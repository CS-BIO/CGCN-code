import networkx as nx
from torch_geometric.data import Data
from torch.utils.data import Dataset, DataLoader
from utils import *
from GraphRicciCurvature.FormanRicci import FormanRicci
from GraphRicciCurvature.OllivierRicci import OllivierRicci


class Data_class(Dataset):

    def __init__(self, triple):
        self.entity1 = triple[:, 0]
        self.entity2 = triple[:, 1]
        self.label = triple[:, 2]

    def __len__(self):
        return len(self.label)

    def __getitem__(self, index):

        return self.label[index], (self.entity1[index], self.entity2[index])


def load_data(args, val_ratio=0.1, test_ratio=0.2):
    """Read data from path, convert data into loader, return features and symmetric adjacency"""
    # read data
    print('Loading {0} seed{1} dataset...'.format(args.in_file[5:8], args.seed))
    positive = np.loadtxt(args.in_file, dtype=np.int64)

    G = nx.Graph()
    G.add_edges_from(positive)
    unique_entity = len(G.nodes)

    link_size = int(positive.shape[0] * args.network_ratio)
    np.random.seed(args.seed)
    np.random.shuffle(positive)
    positive = positive[:link_size]

    G = nx.Graph()
    G.add_edges_from(positive)
    
    for node in G.nodes:
        G.add_edge(node,node)

    orc = OllivierRicci(G, alpha=0.5, verbose="INFO")
    orc.compute_ricci_curvature()
    
    # sample negative
    negative_all = list(nx.non_edges(G))
    np.random.seed(args.seed)
    np.random.shuffle(negative_all)
    negative = np.asarray(negative_all[:positive.shape[0]])
    print("positve examples: %d, negative examples: %d." % (positive.shape[0], negative.shape[0]))

    # split data
    val_size = int(val_ratio * positive.shape[0])
    test_size = int(test_ratio * positive.shape[0])

    positive = np.concatenate([positive, np.ones(positive.shape[0], dtype=np.int64).reshape(positive.shape[0], 1)], axis=1)
    negative = np.concatenate([negative, np.zeros(negative.shape[0], dtype=np.int64).reshape(negative.shape[0], 1)], axis=1)

    train_data = np.vstack((positive[: -(val_size + test_size)], negative[: -(val_size + test_size)]))
    val_data = np.vstack((positive[-(val_size + test_size): -test_size], negative[-(val_size + test_size): -test_size]))
    test_data = np.vstack((positive[-test_size:], negative[-test_size:]))

    # construct adjacency
    train_positive = positive[: -(val_size + test_size)]
    adj = sp.coo_matrix((np.ones(train_positive.shape[0]), (train_positive[:, 0], train_positive[:, 1])),
                        shape=(unique_entity, unique_entity), dtype=np.float32)

    # symmetrization
    adj_o = adj + adj.T.multiply(adj.T > adj) - adj.multiply(adj.T > adj)

    # construct edges
    edges_o = adj_o.nonzero()
    edge_index_o = torch.tensor(np.vstack((edges_o[0], edges_o[1])), dtype=torch.long)

    edge_cuva = []
    for a in range(edge_index_o.shape[1]):
        if edge_index_o[0,a] == edge_index_o[1,a]:
            edge_cuva.append(1)
        else:
            row = edge_index_o[0,a].numpy()
            col = edge_index_o[1,a].numpy()
            edge_cuva.append(orc.G[int(row)][int(col)]["ricciCurvature"])
    
    # build data loader
    params = {'batch_size': args.batch, 'shuffle': True, 'num_workers': args.workers, 'drop_last': True}

    training_set = Data_class(train_data)
    train_loader = DataLoader(training_set, **params)

    validation_set = Data_class(val_data)
    val_loader = DataLoader(validation_set, **params)

    test_set = Data_class(test_data)
    test_loader = DataLoader(test_set, **params)

    # extract features
    print('Extracting features...')
    if args.feature_type == 'one_hot':
        features = np.eye(unique_entity)

    elif args.feature_type == 'uniform':
        np.random.seed(args.seed)
        features = np.random.uniform(low=0, high=1, size=(unique_entity, args.dimensions))

    elif args.feature_type == 'normal':
        np.random.seed(args.seed)
        features = np.random.normal(loc=0, scale=1, size=(unique_entity, args.dimensions))

    elif args.feature_type == 'position':
        features = adj_o.todense()

    features_o = normalize(features)

    args.dimensions = features_o.shape[1]

    edge_cuva_all = torch.tensor(edge_cuva, dtype=torch.float)
    x_o = torch.tensor(features_o, dtype=torch.float)
    data_o = Data(x=x_o, edge_index=edge_index_o, curva=edge_cuva_all) #一阶特征，和边

    print('Loading finished!')
    return data_o, train_loader, val_loader, test_loader
