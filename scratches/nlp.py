import re


def nlp(text):
    re.fullmatch(r'((send ())|(every ())|(to ())|(in ())|(at ()))+', text)
