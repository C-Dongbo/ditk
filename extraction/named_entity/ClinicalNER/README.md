# ClinicalNER
- CliNER 2.0: Accessible and Accurate Clinical Concept Extraction
- W. Boag, E. Sergeeva, S. Kulshreshtha, P. Szolovits, A. Rumshisky, T. Naumann. CliNER 2.0: Accessible and Accurate Clinical Concept Extraction. ML4H: Machine Learning for Health Workshop at NIPS 2017. Long Beach, CA.
- [Paper Link](htt︎ps://arxiv.︎org/p︎df/1803.02245.︎pdf)

## Original Code
https://github.com/text-machine-lab/CliNER

## Description
- Approach 1: CRF with UMLS Features
	* Employ feature extraction using both linguistic features and domain knowledge (Unified Medical Language System)
	* Feed the features into a wrapper for CRFsuite to implement it

<img src="/extraction/named_entity/ClinicalNER/image/appro1.png" width="300">

- Approach 2
	* Employ both word- and character- level bidirectional LSTMs (w+c Bi-LSTM)
	* The embeddings for this sequence of characters are fed into the Bi- LSTM and concatenated to the final forward and backward hidden states to create a character-level representation of the word.
	* Use GloVe to form a rich word- and character- level representation


<img src="/extraction/named_entity/ClinicalNER/image/appro2.png" width="700">

- If you want to run the code in other dataset, please remember to change the labels in [documents.py](/extraction/named_entity/ClinicalNER/code/code/notes/documents.py)

## Input and Output
- Input and output for prediction
	* Input  
		Word pos-tag chunk entity-type ...
	* Output
		Word true-entity-type predict-entity-type

	You can check the test folder for more information.

- Input and output for training  
	Same as Prediction


## Evalution
### Evaluation Datasets
* i2b2 2010
* CoNLL 2003
* OntoNotes 5.0
* CHEMDNER

### Evaluation Metrics
* Precision
* Recall
* F1 Score

### Evaluation Results

|#|i2b2 2010|CoNLL 2003|OntoNotes 5.0|CHEMDNER|
|---|---|---|---|---|
|Precision|83.48%|90.92%|81.95%|80.78%|
|Recall|75.81%|76.27%|66.09%|44.93%|
|F1 Score|79.46%|82.96%|73.17%|57.74%|

![eval](/extraction/named_entity/ClinicalNER/image/eval.png)

## Demo
- [Link to the Jupyter Notebook](/extraction/named_entity/ClinicalNER/code/ClinicalNER.ipynb)
- [Link to the video on Youtube](https://youtu.be/kAJdHhj1VpE)