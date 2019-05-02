from nltk.tokenize import sent_tokenize
from collections import defaultdict
import argparse
import gzip
import sys
import numpy as np
import itertools
import re
import codecs
import json
'''

'''

parser = argparse.ArgumentParser()
parser.add_argument('-i', '--input_file', required=True, help='input file in pubtator format')
parser.add_argument('-d', '--output_dir', required=True, help='write results to this dir')
parser.add_argument('-f', '--output_file_suffix', required=True, help='append this suffix to outfiles')
parser.add_argument('-s', '--max_seq', default=500, help='max sentence length')
parser.add_argument('-a', '--full_abstract', default=False, type=bool, help='full abstracts otherwise sentence segment')
parser.add_argument('-p', '--pubmed_filter', help='Only export abstracts/annotations from these pubmed ids')
parser.add_argument('-r', '--relations', help='two column list of relations to add to annotations')
parser.add_argument('-w', '--word_piece_codes', help='if supplied with codes generated by , uses word pieces to tokenize')
parser.add_argument('-t', '--shards', default=1, help='export data to this many different shards')
parser.add_argument('-x', '--export_all_eps', default=False, type=bool, help='export all ep interactions labeled in the data')
parser.add_argument('-n', '--export_negatives', default=False, type=bool, help='also export documents with no positive interactions')
parser.add_argument('-e', '--encoding', default=None, help='encoding for files')
parser.add_argument('-m', '--max_distance', default=-1, help='throw out examples with mentions too far apart')

args = parser.parse_args()
for arg in vars(args):
    print arg, getattr(args, arg)

# some initial values
current_pub = ''
total_annotations = 0
valid_pubs = 0
pos_interactions = 0
pos_interactions_gold = 0
exported_triples = 0
ENTITY_STRING = 'ENTITY_'
used_annotations = set()
export_types = ['Chemical::Disease']
if args.export_all_eps:
    export_types.append('Chemical::Gene')
    export_types.append('Gene::Disease')
export_types = set(export_types)
pubmed_filter, global_relations = None, None
if args.pubmed_filter:
    with codecs.open(args.pubmed_filter, 'r', args.encoding) as f:
        pubmed_filter = set([l.strip() for l in f])
if args.relations:
    with codecs.open(args.relations, 'r', args.encoding) as f:
        lines = [l.strip().split('\t') for l in f]
        global_relations = dict({(l[0], l[1], l[2]): 'CID' for l in lines}.items() +
                                {('MESH:%s' % l[0], 'MESH:%s' % l[1], l[2]): 'CID' for l in lines}.items() +
                                {('%s' % l[0], 'MESH:%s' % l[1], l[2]): 'CID' for l in lines}.items() +
                                {('MESH:%s' % l[0], '%s' % l[1], l[2]): 'CID' for l in lines}.items())
# either use word piece tokenizer or genia tokenizer
if args.word_piece_codes:
    from word_piece_tokenizer import WordPieceTokenizer
    wpt = WordPieceTokenizer(args.word_piece_codes, entity_str=ENTITY_STRING)
    tokenize = wpt.tokenize
else:
    import genia_tokenizer
    tokenize = genia_tokenizer.tokenize



def make_tsv_line(_e1, e1_mention, e1_type, _e2, e2_mention, e2_type, doc_id, seq_len,
                  e1_start, e1_end, e2_start, e2_end, text, arg_sentence=None, out_label=None):
    """
    generate an output line in 13 column tsv format
    """
    out_text = arg_sentence if arg_sentence is not None else text
    out_label = out_label if out_label is not None else 'Unk'
    out_line = '%s\t%s\t%s\t%s\t%s\t\
                %s\t%s\t%s\t%s\t%s\t\
                %s\t%s\t%s' \
               % (_e1.strip(), e1_type.strip(), e1_mention.strip(), e1_start.strip(), e1_end.strip(),
                  _e2.strip(), e2_type.strip(), e2_mention.strip(), e2_start.strip(), e2_end.strip(),
                  doc_id.strip(), out_label.strip(), out_text.strip())
    # out_line = re.sub(' +', ' ', out_line)
    out_line = re.sub('\\t +', '\t', out_line)
    return out_line+'\n'


def make_examples(doc_id, tokens, entities, filter_entities, label_map, export_arg_sentence=False):
    """
    iterate over entity pairs in this text and export examples
    """
    interactions = 0
    # split multi-token entities and enocde utf
    tokens = [item for sublist in tokens for item in sublist]
    _out_sentence = ' '.join(tokens)
    examples = []
    max_distance = int(args.max_distance)

    grouped_entities = defaultdict(list)
    for tup, _start, _end in entities:
        _mention, _type, _kg_id = tup
        grouped_entities[_kg_id].append((_mention, _type, _kg_id, _start, _end))

    pairs = 0
    for e1_mentions, e2_mentions in itertools.product(grouped_entities.values(), grouped_entities.values()):
        # skip if e1 and e2 are the same mention
        if e1_mentions != e2_mentions:
            pairs += 1
            e1_str = e1_mentions[0][0]
            e2_str = e2_mentions[0][0]
            e1_type = e1_mentions[0][1]
            e2_type = e2_mentions[0][1]
            e1_kg_id = e1_mentions[0][2]
            e2_kg_id = e2_mentions[0][2]
            ep_type = '::'.join([e1_type, e2_type])
            if ep_type in export_types:
                e1_starts = [_start for _, _, _, _start, _end in e1_mentions]
                e1_ends = ':'.join([_end for _, _, _, _start, _end in e1_mentions])
                e2_starts = [_start for _, _, _, _start, _end in e2_mentions]
                e2_ends = ':'.join([_end for _, _, _, _start, _end in e2_mentions])

                if max_distance > 0:
                    e1_s_ints = [int(e1_s) for e1_s in e1_starts]
                    e2_s_ints = [int(e2_s) for e2_s in e2_starts]
                    min_distance = min([(max(e1_s, e2_s)-min(e1_s, e2_s)) for e1_s in e1_s_ints for e2_s in e2_s_ints])
                if max_distance <= 0 or min_distance <= max_distance:
                    if label_map is not None and (e1_kg_id, e2_kg_id, doc_id) in label_map:
                        out_label = label_map[(e1_kg_id, e2_kg_id, doc_id)]
                        interactions += 1
                    elif global_relations is not None and (e1_kg_id, e2_kg_id, doc_id) in global_relations:
                        out_label = global_relations[(e1_kg_id, e2_kg_id, doc_id)]
                        interactions += 1
                    else:
                        out_label = 'Null'

                    example = make_tsv_line(e1_kg_id, e1_str, e1_type, e2_kg_id, e2_str, e2_type, doc_id, len(tokens),
                                            ':'.join(e1_starts), e1_ends, ':'.join(e2_starts), e2_ends,
                                            _out_sentence, out_label=out_label)
                    examples.append((example, out_label))
    return examples, interactions


def make_ner_examples(doc_id, tokens, entities, out_file, filter_entities, label_map):
    starts = {int(start): (int(end), _type, _kg_id) for (_mention, _type, _kg_id), start, end in entities}
    tokens_fixed = [item for sublist in tokens for item in sublist]

    last_end = 0
    ner_examples = []
    for idx, t in enumerate(tokens_fixed):
        bio = ''
        kg_id = '-1'
        if idx in starts:
            last_end, e_type, kg_id = starts[idx]
            bio = 'B-'
        if idx >= last_end:
            e_type = 'O'
        elif idx not in starts:
            bio = 'I-'
        example = '%s\t%s%s\t%s\t%s\n' % (t, bio, e_type, kg_id, doc_id)
        out_file.write(example)
    out_file.write('\n')
    return ner_examples


in_f = gzip.open(args.input_file, 'rb') if args.input_file.endswith('gz') else codecs.open(args.input_file, 'r', args.encoding)
ner_out_file = codecs.open('%s/ner_%s' % (args.output_dir, args.output_file_suffix), 'w', args.encoding)
positive_outs = [codecs.open('%s/positive_%d_%s' % (args.output_dir, i, args.output_file_suffix), 'w', args.encoding)
                 for i in range(0, int(args.shards))]
negative_outs = [codecs.open('%s/negative_%d_%s' % (args.output_dir, i, args.output_file_suffix), 'w', args.encoding)
                 for i in range(0, int(args.shards))]
done = False
# with open(args.output_file, 'w') as out_f:
line_num = 0
last_print = 500
print_every = 500
while not done:
    try:
        if line_num > last_print:
            sys.stdout.write('\rpubs %d annotations: %d lines %d  examples :%d pos_examples: %d'
                         % (valid_pubs, total_annotations, line_num, exported_triples, pos_interactions))
            sys.stdout.flush()
            last_print = line_num + print_every
        line = in_f.readline().strip()
        pub_id, _, title_list = line.split('|', 2)
        line_num += 1
        title = ''.join(title_list)
        abstract = ''.join(in_f.readline().strip().split('|')[2:])
        line_num += 1
        current_pub = '%s %s' % (title, abstract)

        label_annotations = {}
        current_annotations = []
        try:
            line = in_f.readline().strip()
            line_num += 1
            while line:
                parts = line.split('\t')
                if len(parts) == 4:
                    pub_id, rel, e1, e2 = parts
                    label_annotations[(e1, e2, pub_id)] = rel
                    pos_interactions_gold += 1
                elif len(parts) == 6:
                    pub_id, start, end, mention, label, kg_ids = parts
                    for kg_id in kg_ids.split('|'):
                        current_annotations.append((pub_id, int(start), int(end), mention, label, kg_id))
                        total_annotations += 1
                elif len(parts) == 7:
                    pub_id, start, end, mention, label, kg_ids, split_mentions = parts
                    for kg_id in kg_ids.split('|'):
                        current_annotations.append((pub_id, int(start), int(end), mention, label, kg_id))
                        total_annotations += 1
                # else:
                #     print('weird number of fields for annotations: %s' % line)
                line = in_f.readline().strip()
                line_num += 1

            if not pubmed_filter or pub_id in pubmed_filter:
                # do something with last annotations
                valid_pubs += 1
                sorted_annotations = sorted(current_annotations, key=lambda tup: tup[1])
                replaced_text = []
                last = 0
                annotation_map = {}
                for i, (pub_id, start, end, mention, label, kg_id) in enumerate(sorted_annotations):
                    mention = current_pub[start:end]
                    dummy_token = '%s%d_' % (ENTITY_STRING, i)
                    replaced_text.append(' %s %s ' % (current_pub[last:start].strip(), dummy_token))
                    last = end
                    annotation_map[dummy_token] = (mention, label, kg_id)

                # add text that occurs after the last entity
                replaced_text.append(current_pub[end:])
                abstract = ''.join(replaced_text).replace('  ', ' ')
                sentences = [abstract] if args.full_abstract else sent_tokenize(abstract)
                entity_counts = [(s.count(ENTITY_STRING), s) for s in sentences]

                tokenized_sentences = [[w for w in tokenize(s)] for s in sentences]

                valid_tokenized_sentences = [s for s in tokenized_sentences if len(s) <= args.max_seq]
                out_sentence = [[tokenize(annotation_map[token][0]) if token.startswith(ENTITY_STRING) else [token]
                                 for token in sentence]
                                for sentence in valid_tokenized_sentences]

                # get the token offsets in the sentence for each entity
                token_lens = [[len(token) if type(token) is list else 1 for token in sentence] for sentence in out_sentence]
                token_offsets = [np.cumsum(lens) for lens in token_lens]

                entity_offsets = [[(annotation_map[token], str(offset[i] - length[i]), str(offset[i]))
                                   for (i, token) in enumerate(sentence) if token.startswith(ENTITY_STRING)]
                                  for length, offset, sentence
                                  in zip(token_lens, token_offsets, valid_tokenized_sentences)]
                out_examples = [make_examples(pub_id, sent, offset, filter_entities=None, label_map=label_annotations)
                                for sent, offset in zip(out_sentence, entity_offsets)]

                for ex_pos_count in out_examples:
                    ex_label, pos_count = ex_pos_count
                    if ex_label and (pos_count > 0 or args.export_negatives):
                        # ex, out_labels = zip(*ex)
                        pos_interactions += pos_count
                        exported_triples += len(ex_label)
                        positive_examples = [ex for ex, out_label in ex_label if out_label != 'Null']
                        negative_examples = [ex for ex, out_label in ex_label if out_label == 'Null']
                        shard_id = np.random.randint(0, int(args.shards))
                        if positive_examples: positive_outs[shard_id].write((''.join(positive_examples)))
                        if negative_examples: negative_outs[shard_id].write((''.join(negative_examples)))
                if ner_out_file:
                    [make_ner_examples(pub_id, sent, offset, ner_out_file, filter_entities=None, label_map=label_annotations)
                     for sent, offset in zip(out_sentence, entity_offsets)]

        except Exception as e:
            print(line_num)
            print('Error: %s' % e)
    except Exception as e2:
        done = True
        in_f.close()
        ner_out_file.close()
        for i in range(0, int(args.shards)):
            positive_outs[shard_id].close()
            negative_outs[shard_id].close()

sys.stdout.write('\rpubs %d  annotations: %d   lines %d  examples :%d  pos_examples: %d   pos_example_annotations %d\n'
      % (valid_pubs, total_annotations, line_num, exported_triples, pos_interactions, pos_interactions_gold))
sys.stdout.flush()