from __future__ import print_function
import datetime
import time
import torch
import torch.autograd as autograd
import torch.nn as nn
import torch.optim as optim
import codecs
from model.crf import *
from model.lm_lstm_crf import *
import model.utils as utils
from model.evaluator import eval_wc

from hparams import hparams as hp

import argparse
import json
import os
import sys
from tqdm import tqdm
import itertools
import functools

def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

if __name__ == "__main__":
    import sys, os

    # set path to ditk root
    ditk_path = os.path.abspath(os.getcwd())
    if ditk_path not in sys.path:
        sys.path.append(ditk_path)

    data_dir = os.path.join(ditk_path, 'extraction/named_entity/lmlstmcrf')
        
    emb_file = data_dir + "/embedding/test.embedding"
    train_file = data_dir + "/data/ner/out_test.train"
    dev_file = data_dir + "/data/ner/out.testa"
    test_file = data_dir + "/data/ner/out.testb"
    hp.checkpoint_dir = data_dir + "/checkpoint/"
    hp.emb_file = emb_file
    if not os.path.exists(hp.checkpoint_dir):
        os.makedirs(hp.checkpoint_dir)

    args = hp
    if args.gpu >= 0:
        torch.cuda.set_device(args.gpu)

    print('setting:')
    print(args)

    # load corpus
    print('loading corpus')
    with codecs.open(train_file, 'r', 'utf-8') as f:
        lines = f.readlines()
    with codecs.open(dev_file, 'r', 'utf-8') as f:
        dev_lines = f.readlines()
    with codecs.open(test_file, 'r', 'utf-8') as f:
        test_lines = f.readlines()

    dev_features, dev_labels = utils.read_corpus(dev_lines)
    test_features, test_labels = utils.read_corpus(test_lines)

    if args.load_check_point:
        if os.path.isfile(args.checkpoint):
            print("loading checkpoint: '{}'".format(args.checkpoint))
            checkpoint_file = torch.load(args.checkpoint, map_location='cpu')
            args.start_epoch = checkpoint_file['epoch']
            f_map = checkpoint_file['f_map']
            l_map = checkpoint_file['l_map']
            c_map = checkpoint_file['c_map']
            in_doc_words = checkpoint_file['in_doc_words']
            train_features, train_labels = utils.read_corpus(lines)
        else:
            print("no checkpoint found at: '{}'".format(args.checkpoint))
    else:
        print('constructing coding table')

        # converting format
        train_features, train_labels, f_map, l_map, c_map = utils.generate_corpus_char(lines, if_shrink_c_feature=True, c_thresholds=args.mini_count, if_shrink_w_feature=False)
        
        f_set = {v for v in f_map}
        f_map = utils.shrink_features(f_map, train_features, args.mini_count)

        dt_f_set = functools.reduce(lambda x, y: x | y, map(lambda t: set(t), dev_features), f_set)
        dt_f_set = functools.reduce(lambda x, y: x | y, map(lambda t: set(t), test_features), dt_f_set)
        print("feature size: '{}'".format(len(f_map)))
        print('loading embedding')
        if args.fine_tune:  # which means does not do fine-tune
            f_map = {'<eof>': 0}
        f_map, embedding_tensor, in_doc_words = utils.load_embedding_wlm(emb_file, ' ', f_map, dt_f_set, args.caseless, args.unk, args.word_dim, shrink_to_corpus=args.shrink_embedding)
        print("embedding size: '{}'".format(len(f_map)))

        l_set = functools.reduce(lambda x, y: x | y, map(lambda t: set(t), dev_labels))
        l_set = functools.reduce(lambda x, y: x | y, map(lambda t: set(t), test_labels), l_set)
        for label in l_set:
            if label not in l_map:
                l_map[label] = len(l_map)
    
    print('constructing dataset')
    # construct dataset
    dataset, forw_corp, back_corp = utils.construct_bucket_mean_vb_wc(train_features, train_labels, l_map, c_map, f_map, args.caseless)
    dev_dataset, forw_dev, back_dev = utils.construct_bucket_mean_vb_wc(dev_features, dev_labels, l_map, c_map, f_map, args.caseless)
    test_dataset, forw_test, back_test = utils.construct_bucket_mean_vb_wc(test_features, test_labels, l_map, c_map, f_map, args.caseless)
    
    dataset_loader = [torch.utils.data.DataLoader(tup, args.batch_size, shuffle=True, drop_last=False) for tup in dataset]
    dev_dataset_loader = [torch.utils.data.DataLoader(tup, 50, shuffle=False, drop_last=False) for tup in dev_dataset]
    test_dataset_loader = [torch.utils.data.DataLoader(tup, 50, shuffle=False, drop_last=False) for tup in test_dataset]

    # build model
    print('building model')
    ner_model = LM_LSTM_CRF(len(l_map), len(c_map), args.char_dim, args.char_hidden, args.char_layers, args.word_dim, args.word_hidden, args.word_layers, len(f_map), args.drop_out, large_CRF=args.small_crf, if_highway=args.high_way, in_doc_words=in_doc_words, highway_layers = args.highway_layers)

    if args.load_check_point:
        ner_model.load_state_dict(checkpoint_file['state_dict'])
    else:
        if not args.rand_embedding:
            ner_model.load_pretrained_word_embedding(embedding_tensor)
        ner_model.rand_init(init_word_embedding=args.rand_embedding)

    if args.update == 'sgd':
        optimizer = optim.SGD(ner_model.parameters(), lr=args.lr, momentum=args.momentum)
    elif args.update == 'adam':
        optimizer = optim.Adam(ner_model.parameters(), lr=args.lr)

    if args.load_check_point and args.load_opt:
        optimizer.load_state_dict(checkpoint_file['optimizer'])

    crit_lm = nn.CrossEntropyLoss()
    crit_ner = CRFLoss_vb(len(l_map), l_map['<start>'], l_map['<pad>'])

    if args.gpu >= 0:
        if_cuda = True
        print('device: ' + str(args.gpu))
        torch.cuda.set_device(args.gpu)
        crit_ner.cuda()
        crit_lm.cuda()
        ner_model.cuda()
        packer = CRFRepack_WC(len(l_map), True)
    else:
        if_cuda = False
        packer = CRFRepack_WC(len(l_map), False)

    tot_length = sum(map(lambda t: len(t), dataset_loader))

    best_f1 = float('-inf')
    best_acc = float('-inf')
    track_list = list()
    start_time = time.time()
    epoch_list = range(args.start_epoch, args.start_epoch + args.epoch)
    patience_count = 0

    evaluator = eval_wc(packer, l_map, args.eva_matrix)

    for epoch_idx, args.start_epoch in enumerate(epoch_list):

        epoch_loss = 0
        ner_model.train()
        for f_f, f_p, b_f, b_p, w_f, tg_v, mask_v, len_v in tqdm(
                itertools.chain.from_iterable(dataset_loader), mininterval=2,
                desc=' - Tot it %d (epoch %d)' % (tot_length, args.start_epoch), leave=False, file=sys.stdout):
            f_f, f_p, b_f, b_p, w_f, tg_v, mask_v = packer.repack_vb(f_f, f_p, b_f, b_p, w_f, tg_v, mask_v, len_v)
            ner_model.zero_grad()
            scores = ner_model(f_f, f_p, b_f, b_p, w_f)
            loss = crit_ner(scores, tg_v, mask_v)
            epoch_loss += utils.to_scalar(loss)
            if args.co_train:
                cf_p = f_p[0:-1, :].contiguous()
                cb_p = b_p[1:, :].contiguous()
                cf_y = w_f[1:, :].contiguous()
                cb_y = w_f[0:-1, :].contiguous()
                cfs, _ = ner_model.word_pre_train_forward(f_f, cf_p)
                loss = loss + args.lambda0 * crit_lm(cfs, cf_y.view(-1))
                cbs, _ = ner_model.word_pre_train_backward(b_f, cb_p)
                loss = loss + args.lambda0 * crit_lm(cbs, cb_y.view(-1))
            loss.backward()
            nn.utils.clip_grad_norm_(ner_model.parameters(), args.clip_grad)
            optimizer.step()
        epoch_loss /= tot_length

        # update lr
        if args.update == 'sgd':
            utils.adjust_learning_rate(optimizer, args.lr / (1 + (args.start_epoch + 1) * args.lr_decay))

        # eval & save check_point

        if 'f' in args.eva_matrix:
            dev_result = evaluator.calc_score(ner_model, dev_dataset_loader)
            for label, (dev_f1, dev_pre, dev_rec, dev_acc, msg) in dev_result.items():
                print('DEV : %s : dev_f1: %.4f dev_rec: %.4f dev_pre: %.4f dev_acc: %.4f | %s\n' % (label, dev_f1, dev_rec, dev_pre, dev_acc, msg))
            (dev_f1, dev_pre, dev_rec, dev_acc, msg) = dev_result['total']
            
            track_list.append(dev_result)

            if dev_f1 > best_f1:
                patience_count = 0
                best_f1 = dev_f1

                test_result = evaluator.calc_score(ner_model, test_dataset_loader)
                for label, (test_f1, test_pre, test_rec, test_acc, msg) in test_result.items():
                    print('TEST : %s : test_f1: %.4f test_rec: %.4f test_pre: %.4f test_acc: %.4f | %s\n' % (label, test_f1, test_rec, test_pre, test_acc, msg))
                (test_f1, test_rec, test_pre, test_acc, msg) = test_result['total']

                # track_list.append(
                #     {'loss': epoch_loss, 'dev_f1': dev_f1, 'dev_acc': dev_acc, 'test_f1': test_f1,
                #      'test_acc': test_acc})

                print(
                    '(loss: %.4f, epoch: %d, dev F1 = %.4f, dev acc = %.4f, F1 on test = %.4f, acc on test= %.4f), saving...' %
                    (epoch_loss,
                     args.start_epoch,
                     dev_f1,
                     dev_acc,
                     test_f1,
                     test_acc))

                try:
                    utils.save_checkpoint({
                        'epoch': args.start_epoch,
                        'state_dict': ner_model.state_dict(),
                        'optimizer': optimizer.state_dict(),
                        'f_map': f_map,
                        'l_map': l_map,
                        'c_map': c_map,
                        'in_doc_words': in_doc_words
                    }, {'track_list': track_list
                        }, args.checkpoint_dir + 'cwlm_lstm_crf')
                except Exception as inst:
                    print(inst)

            else:
                patience_count += 1
                print('(loss: %.4f, epoch: %d, dev F1 = %.4f, dev acc = %.4f)' %
                      (epoch_loss,
                       args.start_epoch,
                       dev_f1,
                       dev_acc))
                track_list.append({'loss': epoch_loss, 'dev_f1': dev_f1, 'dev_acc': dev_acc})

        else:

            dev_acc = evaluator.calc_score(ner_model, dev_dataset_loader)

            if dev_acc > best_acc:
                patience_count = 0
                best_acc = dev_acc
                
                test_acc = evaluator.calc_score(ner_model, test_dataset_loader)

                track_list.append(
                    {'loss': epoch_loss, 'dev_acc': dev_acc, 'test_acc': test_acc})

                print(
                    '(loss: %.4f, epoch: %d, dev acc = %.4f, acc on test= %.4f), saving...' %
                    (epoch_loss,
                     args.start_epoch,
                     dev_acc,
                     test_acc))

                try:
                    utils.save_checkpoint({
                        'epoch': args.start_epoch,
                        'state_dict': ner_model.state_dict(),
                        'optimizer': optimizer.state_dict(),
                        'f_map': f_map,
                        'l_map': l_map,
                        'c_map': c_map,
                        'in_doc_words': in_doc_words
                    }, {'track_list': track_list,
                        'args': vars(args)
                        }, args.checkpoint_dir + 'cwlm_lstm_crf')
                except Exception as inst:
                    print(inst)

            else:
                patience_count += 1
                print('(loss: %.4f, epoch: %d, dev acc = %.4f)' %
                      (epoch_loss,
                       args.start_epoch,
                       dev_acc))
                track_list.append({'loss': epoch_loss, 'dev_acc': dev_acc})

        print('epoch: ' + str(args.start_epoch) + '\t in ' + str(args.epoch) + ' take: ' + str(
            time.time() - start_time) + ' s')

        if patience_count >= args.patience and args.start_epoch >= args.least_iters:
            break

    #print best
    if 'f' in args.eva_matrix:
        eprint(args.checkpoint_dir + ' dev_f1: %.4f dev_rec: %.4f dev_pre: %.4f dev_acc: %.4f test_f1: %.4f test_rec: %.4f test_pre: %.4f test_acc: %.4f\n' % (dev_f1, dev_rec, dev_pre, dev_acc, test_f1, test_rec, test_pre, test_acc))
    else:
        eprint(args.checkpoint_dir + ' dev_acc: %.4f test_acc: %.4f\n' % (dev_acc, test_acc))
    
    utils.save_checkpoint({
        'epoch': args.start_epoch,
        'state_dict': ner_model.state_dict(),
        'optimizer': optimizer.state_dict(),
        'f_map': f_map,
        'l_map': l_map,
        'c_map': c_map,
        'in_doc_words': in_doc_words
    }, {'track_list': track_list
        }, args.checkpoint_dir + 'cwlm_lstm_crf')
    # printing summary
    print('setting:')
    print(args)
