import os
import itertools
import collections
import json
from collections import defaultdict
from tqdm import tqdm
import numpy as np
import torch
from torchtext.vocab import GloVe
from torchtext.vocab import build_vocab_from_iterator

from embedding.avg import AVG
from embedding.cxtebd import CXTEBD
from embedding.wordebd import WORDEBD
import data.stats as stats
from data.utils import tprint

from transformers import BertTokenizer


def _get_20newsgroup_classes():
    '''
        @return list of classes associated with each split
    '''
    label_dict = {
        'talk.politics.mideast': 0,
        'sci.space': 1,
        'misc.forsale': 2,
        'talk.politics.misc': 3,
        'comp.graphics': 4,
        'sci.crypt': 5,
        'comp.windows.x': 6,
        'comp.os.ms-windows.misc': 7,
        'talk.politics.guns': 8,
        'talk.religion.misc': 9,
        'rec.autos': 10,
        'sci.med': 11,
        'comp.sys.mac.hardware': 12,
        'sci.electronics': 13,
        'rec.sport.hockey': 14,
        'alt.atheism': 15,
        'rec.motorcycles': 16,
        'comp.sys.ibm.pc.hardware': 17,
        'rec.sport.baseball': 18,
        'soc.religion.christian': 19,
    }

    train_classes = []
    for key in label_dict.keys():
        if key[:key.find('.')] in ['sci', 'rec']:
            train_classes.append(label_dict[key])

    val_classes = []
    for key in label_dict.keys():
        if key[:key.find('.')] in ['comp']:
            val_classes.append(label_dict[key])

    test_classes = []
    for key in label_dict.keys():
        if key[:key.find('.')] not in ['comp', 'sci', 'rec']:
            test_classes.append(label_dict[key])

    return train_classes, val_classes, test_classes


def _get_amazon_classes():
    '''
        @return list of classes associated with each split
    '''
    label_dict = {
        'Amazon_Instant_Video': 0,
        'Apps_for_Android': 1,
        'Automotive': 2,
        'Baby': 3,
        'Beauty': 4,
        'Books': 5,
        'CDs_and_Vinyl': 6,
        'Cell_Phones_and_Accessories': 7,
        'Clothing_Shoes_and_Jewelry': 8,
        'Digital_Music': 9,
        'Electronics': 10,
        'Grocery_and_Gourmet_Food': 11,
        'Health_and_Personal_Care': 12,
        'Home_and_Kitchen': 13,
        'Kindle_Store': 14,
        'Movies_and_TV': 15,
        'Musical_Instruments': 16,
        'Office_Products': 17,
        'Patio_Lawn_and_Garden': 18,
        'Pet_Supplies': 19,
        'Sports_and_Outdoors': 20,
        'Tools_and_Home_Improvement': 21,
        'Toys_and_Games': 22,
        'Video_Games': 23
    }

    train_classes = [2, 3, 4, 7, 11, 12, 13, 18, 19, 20]
    val_classes = [1, 22, 23, 6, 9]
    test_classes = [0, 5, 14, 15, 8, 10, 16, 17, 21]

    return train_classes, val_classes, test_classes


def _get_rcv1_classes():
    '''
        @return list of classes associated with each split
    '''

    train_classes = [1, 2, 12, 15, 18, 20, 22, 25, 27, 32, 33, 34, 38, 39,
                     40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53,
                     54, 55, 56, 57, 58, 59, 60, 61, 66]
    val_classes = [5, 24, 26, 28, 29, 31, 35, 23, 67, 36]
    test_classes = [0, 3, 4, 6, 7, 8, 9, 10, 11, 13, 14, 16, 17, 19, 21, 30, 37,
                    62, 63, 64, 65, 68, 69, 70]

    return train_classes, val_classes, test_classes


def _get_fewrel_classes():
    '''
        @return list of classes associated with each split
    '''
    # head=WORK_OF_ART validation/test split
    train_classes = [0, 1, 2, 3, 4, 5, 6, 8, 10, 11, 12, 13, 14, 15, 16, 19, 21,
                     22, 24, 25, 26, 27, 28, 30, 31, 32, 33, 34, 35, 36, 37, 38,
                     39, 40, 41, 43, 44, 45, 46, 48, 49, 50, 52, 53, 56, 57, 58,
                     59, 61, 62, 63, 64, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75,
                     76, 77, 78]

    val_classes = [7, 9, 17, 18, 20]
    test_classes = [23, 29, 42, 47, 51, 54, 55, 60, 65, 79]

    return train_classes, val_classes, test_classes


def _get_huffpost_classes():
    '''
        @return list of classes associated with each split
    '''

    train_classes = list(range(20))
    val_classes = list(range(20, 25))
    test_classes = list(range(25, 41))

    return train_classes, val_classes, test_classes


def _get_reuters_classes():
    '''
        @return list of classes associated with each split
    '''

    train_classes = list(range(15))
    val_classes = list(range(15, 20))
    test_classes = list(range(20, 31))

    return train_classes, val_classes, test_classes


def _load_json(path):
    '''
        load data file
        @param path: str, path to the data file
        @return data: list of examples
    '''
    label = {}
    text_len = []
    with open(path, 'r', errors='ignore') as f:
        data = []
        for line in f:
            row = json.loads(line)

            # count the number of examples per label
            if int(row['label']) not in label:
                label[int(row['label'])] = 1
            else:
                label[int(row['label'])] += 1

            item = {
                'label': int(row['label']),
                'text': row['text'][:500]  # truncate the text to 500 tokens
            }

            text_len.append(len(row['text']))

            keys = ['head', 'tail', 'ebd_id']
            for k in keys:
                if k in row:
                    item[k] = row[k]

            data.append(item)

        print('Class balance:')

        print(label)

        print('Avg len: {}'.format(sum(text_len) / (len(text_len))))

        return data


def _read_words(data):
    '''
        Count the occurrences of all words
        @param data: list of examples
        @return words: list of words (with duplicates)
    '''
    words = []
    for example in data:
        words += example['text']
    return words


def _meta_split(all_data, train_classes, val_classes, test_classes):
    '''
        Split the dataset according to the specified train_classes, val_classes
        and test_classes

        @param all_data: list of examples (dictionaries)
        @param train_classes: list of int
        @param val_classes: list of int
        @param test_classes: list of int

        @return train_data: list of examples
        @return val_data: list of examples
        @return test_data: list of examples
    '''
    train_data, val_data, test_data = [], [], []

    for example in all_data:
        if example['label'] in train_classes:
            train_data.append(example)
        if example['label'] in val_classes:
            val_data.append(example)
        if example['label'] in test_classes:
            test_data.append(example)

    return train_data, val_data, test_data


def _del_by_idx(array_list, idx, axis):
    '''
        Delete the specified index for each array in the array_lists

        @params: array_list: list of np arrays
        @params: idx: list of int
        @params: axis: int

        @return: res: tuple of pruned np arrays
    '''
    if type(array_list) is not list:
        array_list = [array_list]

    # modified to perform operations in place
    for i, array in enumerate(array_list):
        array_list[i] = np.delete(array, idx, axis)

    if len(array_list) == 1:
        return array_list[0]
    else:
        return array_list


def _data_to_nparray(data, vocab, vocab_size, max_text_len=None):
    '''
        Convert the data into a dictionary of np arrays for speed.
    '''
    doc_label = np.array([x['label'] for x in data], dtype=np.int64)

    raw = np.array([e['text'] for e in data], dtype=object)

    # compute the max text length
    text_len = np.array([len(e['text']) for e in data])
    if max_text_len==None:
        max_text_len = max(text_len)

    # initialize the big numpy array by <pad>
    text = vocab.get_stoi()['<pad>'] * np.ones([len(data), max_text_len],
                                               dtype=np.int64)
    print('max_len', max_text_len)

    del_idx = []
    # convert each token to its corresponding id
    for i in range(len(data)):

        # text[i, :len(data[i]['text'])] = [
        #        vocab.get_stoi()[x] if x in vocab.get_stoi() else vocab.get_stoi()['<unk>']
        #        for x in data[i]['text']]
        text[i, :len(data[i]['text'])] = vocab(data[i]['text'])

        # filter out document with only unk and pad
        if np.max(text[i]) < 2:
            del_idx.append(i)

    # vocab_size = vocab.vectors.size()[0]

    text_len, text, doc_label, raw = _del_by_idx(
        [text_len, text, doc_label, raw], del_idx, 0)

    new_data = {
        'text': text,
        'text_len': text_len,
        'label': doc_label,
        'raw': raw,
        'vocab_size': vocab_size,
    }

    return new_data


def data_to_nparray(data, stoi, vocab_size, max_text_len=None):
    '''
        Convert the data into a dictionary of np arrays for speed.
    '''
    doc_label = np.array([x['label'] for x in data], dtype=np.int64)

    raw = np.array([e['text'] for e in data], dtype=object)

    # compute the max text length
    text_len = np.array([len(e['text']) for e in data])
    if max_text_len==None:
        max_text_len = max(text_len)

    # initialize the big numpy array by <pad>
    text = stoi['<pad>'] * np.ones([len(data), max_text_len],
                                               dtype=np.int64)
    print('max_len', max_text_len)

    del_idx = []
    # convert each token to its corresponding id
    for i in range(len(data)):

        text[i, :len(data[i]['text'])] = [
                stoi[x] if x in stoi else stoi['unk']
                for x in data[i]['text']]
        #text[i, :len(data[i]['text'])] = stoi(data[i]['text'])

        # filter out document with only unk and pad
        if np.max(text[i]) < 2:
            del_idx.append(i)

    # vocab_size = vocab.vectors.size()[0]

    #text_len, text, doc_label, raw = _del_by_idx(
    #    [text_len, text, doc_label, raw], del_idx, 0)

    new_data = {
        'text': text,
        'text_len': text_len,
        'label': doc_label,
        'raw': raw,
        'vocab_size': vocab_size,
    }

    return new_data


def _split_dataset(data, finetune_split):
    """
        split the data into train and val (maintain the balance between classes)
        @return data_train, data_val
    """

    # separate train and val data
    # used for fine tune
    data_train, data_val = defaultdict(list), defaultdict(list)

    # sort each matrix by ascending label order for each searching
    idx = np.argsort(data['label'], kind="stable")

    non_idx_keys = ['vocab_size', 'classes2id', 'is_train']
    for k, v in data.items():
        if k not in non_idx_keys:
            data[k] = v[idx]

    # loop through classes in ascending order
    classes, counts = np.unique(data['label'], return_counts=True)
    start = 0
    for label, n in zip(classes, counts):
        mid = start + int(finetune_split * n)  # split between train/val
        end = start + n  # split between this/next class

        for k, v in data.items():
            if k not in non_idx_keys:
                data_train[k].append(v[start:mid])
                data_val[k].append(v[mid:end])

        start = end  # advance to next class

    # convert back to np arrays
    for k, v in data.items():
        if k not in non_idx_keys:
            data_train[k] = np.concatenate(data_train[k], axis=0)
            data_val[k] = np.concatenate(data_val[k], axis=0)

    return data_train, data_val


def load_dataset(datadir, dataset, args=None):


    if dataset == '20newsgroup':
        train_classes, val_classes, test_classes = _get_20newsgroup_classes()
    elif dataset == 'amazon':
        train_classes, val_classes, test_classes = _get_amazon_classes()
    elif dataset == 'fewrel':
        train_classes, val_classes, test_classes = _get_fewrel_classes()
    elif dataset == 'huffpost':
        train_classes, val_classes, test_classes = _get_huffpost_classes()
    elif dataset == 'reuters':
        train_classes, val_classes, test_classes = _get_reuters_classes()
    elif dataset == 'rcv1':
        train_classes, val_classes, test_classes = _get_rcv1_classes()
    else:
        raise ValueError(
            'args.dataset should be one of'
            '[20newsgroup, amazon, fewrel, huffpost, reuters, rcv1]')

    # assert(len(train_classes) == args.n_train_class)
    # assert(len(val_classes) == args.n_val_class)
    # assert(len(test_classes) == args.n_test_class)

    print(train_classes)
    print(test_classes)

    print('Loading data')
    all_data = _load_json('./data/text-data/' + dataset + '.json')

    print('Loading word vectors')
    # path = os.path.join('./', 'wiki.en.vec')
    path = os.path.join('./', 'glove.42B.300d.txt')
    if not os.path.exists(path):
        # Download the word vector and save it locally:
        print('Downloading word vectors')
        import urllib.request
        urllib.request.urlretrieve(
            'https://dl.fbaipublicfiles.com/fasttext/vectors-wiki/wiki.en.vec',
            path)

    #vectors = Vectors('wiki.en.vec', cache='./')
    vectors=GloVe(name='42B', dim=300)
    print(vectors)

    # 1. Create an iterator that yields lists of tokens
    def yield_tokens(data_iter):
        for example in data_iter:
            yield example['text']

    # 2. Build the vocabulary using the new API
    Vocab = build_vocab_from_iterator(
        yield_tokens(all_data),
        specials=['<pad>', '<unk>'],
        min_freq=5
    )
    # 3. Set the default index for out-of-vocabulary words
    Vocab.set_default_index(Vocab['<unk>'])
    
    # Vocab.insert_token('<pad>',32135)
    print('vocab size:', len(Vocab.get_stoi()))
    Vocab.set_default_index(32137)

    print(len(vectors.stoi))





    # print word embedding statistics
    # wv_size = vocab.vectors.size()
    wv_size = vectors.vectors.size()
    print('Total num. of words: {}, word vector dimension: {}'.format(
        wv_size[0],
        wv_size[1]))

    # num_oov = wv_size[0] - torch.nonzero(
    #        torch.sum(torch.abs(vocab.vectors), dim=1)).size()[0]
    # tprint(('Num. of out-of-vocabulary words'
    #       '(they are initialized to zeros): {}').format( num_oov))

    # Split into meta-train, meta-val, meta-test data
    train_data, val_data, test_data = _meta_split(
        all_data, train_classes, val_classes, test_classes)
    print('#train {}, #val {}, #test {}'.format(
        len(train_data), len(val_data), len(test_data)))

    # Convert everything into np array for fast data loading

    if dataset=='20newsgroup':
        max_text_len=500
    elif dataset=='fewrel':
        max_text_len=38
    else:
        max_text_len=44

    train_data = data_to_nparray(train_data, vectors.stoi, wv_size[0], max_text_len=max_text_len)
    val_data = data_to_nparray(val_data, vectors.stoi, wv_size[0], max_text_len=max_text_len)
    test_data = data_to_nparray(test_data, vectors.stoi, wv_size[0], max_text_len=max_text_len)

    print(train_data['text'].shape)

    train_data['is_train'] = True
    # this tag is used for distinguishing train/val/test when creating source pool

    # stats.precompute_stats(train_data, val_data, test_data, args)

    return train_data, val_data, test_data  # , vocab
