import re


word_dict = {
    'sec': 1,
    'second': 1,

    'min': 60,
    'minute': 60,

    'hr': 3600,
    'hour': 3600,

    'day': 86400,
}

class Word:
    @staticmethod
    def interpret(text):


    def __init__(self, word):
        self.text = word
        self.next = None

    def valuate(self):
        pass

    def is_numeric(self):
        return True if all(x in '0123456789' for x in self.text) else False

class Multiplier(Word):
    def valuate(self):

class Duration:
    def __init__(self, word):


        self.length = length

class Combination:

def match_type(word):


def process(text):
    words = re.findall(r'(\S+)', text.lower())

    map(match_type, words)