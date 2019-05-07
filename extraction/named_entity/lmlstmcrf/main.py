import sys, os

# set path to ditk root
ditk_path = os.path.abspath(os.getcwd())
if ditk_path not in sys.path:
    sys.path.append(ditk_path)

data_dir = os.path.join(ditk_path, 'extraction/named_entity/lmlstmcrf')

data_sets = ['conll', 'ontonotes', 'chemdner']

emb_file = data_dir + "/embedding/glove.6B.100d.embedding"

chosen_type = data_sets[0]
train_file = data_dir + "/data/{}/out.train".format(chosen_type)
dev_file = data_dir + "/data/{}/out.testa".format(chosen_type)
test_file = data_dir + "/data/{}/out.testb".format(chosen_type)

from extraction.named_entity.lmlstmcrf.hparams import hparams as hp
from extraction.named_entity.lmlstmcrf.lmlstmcrf import Lmlstmcrf

# set hparam files
hp.checkpoint_dir = data_dir + "/checkpoint/"
hp.checkpoint = data_dir + "/checkpoint/conll.model"
hp.emb_file = emb_file
hp.gpu = -1

if not os.path.exists(hp.checkpoint_dir):
    os.makedirs(hp.checkpoint_dir)

model = Lmlstmcrf()

data = model.read_dataset({
    "train": train_file,
    "test": test_file,
    "dev": dev_file,
})

model.load_model(hp.checkpoint)

# model.train(data)

predictions = model.predict(data)

score = model.evaluate(predictions, data)

print(score)