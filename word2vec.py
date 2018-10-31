import os
import pandas as pd
import nltk
import gensim
from gensim import corpora, models, similarities

os.chdir("D:\semicolon\Deep Learning");
df = pd.read_csv('jokes.csv');

x = df['Question'].values.tolist()
y = df['Answer'].values.tolist()

corpus = x + y

tok_corp = [nltk.word_tokenize(sent.decode('utf-8')) for sent in corpus]

model = gensim.models.Word2Vec(tok_corp, min_count=1, size=32)

# model.save('testmodel')
# model = gensim.models.Word2Vec.load('test_model')
# model.most_similar('word')
# model.most_similar([vector])