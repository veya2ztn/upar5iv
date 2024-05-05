import re
from lxml import etree
from typing import Dict
from copy import deepcopy
import lxml,copy
import logging
import os
prepositions = {'at', 'in', 'on', 'for', 'with', 'and','see', 'or', 
                'nor', 'about', 'as', 'by', 'over', 
                'according to', 'against', 'along', 'among', 
                'apart from', 'around', 'as for', 'aside from', 
                'because of', 'before', 'behind', 'below', 
                'beneath', 'beside', 'between', 'beyond', 
                'but', 'by means of', 'concerning', 
                'despite', 'down', 'due to', 'during', 'except', 
                'except for', 'in addition to', 'in case of', 
                'in front of', 'in place of', 'in spite of', 
                'inside', 'instead of', 'into', 'like', 'near', 'next', 
                'off', 'onto', 'out', 'out of', 'outside', 'over', 'past', 
                'since', 'through', 'throughout', 'toward', 'under', 
                'underneath', 'until', 'up', 'upon', 'with', 'within', 
                'without'}
PATTERN_END_REF = "|".join(["(?<=\s|\(|\{|\[)"+k+"$|^"+k+"$" for k in ['ref', 'refs', 'papers', 'paper','reference','references']])
PATTERN_END_FIG = "|".join(["(?<=\s|\(|\{|\[)"+k+"$|^"+k+"$" for k in ['fig', 'figures', 'figs', 'figure']])
PATTERN_END_TAB = "|".join(["(?<=\s|\(|\{|\[)"+k+"$|^"+k+"$" for k in ['tab', 'tables', 'tabs', 'table']])
PATTERN_END_SEC = "|".join(["(?<=\s|\(|\{|\[)"+k+"$|^"+k+"$" for k in ['sec', 'section']])
PATTERN_END_EQU = "|".join(["(?<=\s|\(|\{|\[)"+k+"$|^"+k+"$" for k in ['eq', 'equ', 'equation', 'equations','formula','formulas']])
PATTERN_END_CHP = "|".join(["(?<=\s|\(|\{|\[)"+k+"$|^"+k+"$" for k in ['chapter','chapters','chpt','chpts']])

class KnowError(NotImplementedError):pass
class MathDontHaveTex(NotImplementedError):pass
class MisMatchRefError(NotImplementedError):pass
class CiteDontHaveBibRefError(NotImplementedError):pass
class TooManyNoteError(NotImplementedError):pass
class PleaseCheckError(NotImplementedError):pass
class InfinityLoop(NotImplementedError):pass

class LoopCounter:
    def __init__(self, max_iterations=100):
        self.max_iterations = max_iterations
        self.counter = 0

    def increment(self):
        self.counter += 1
        if self.counter >= self.max_iterations:
            raise InfinityLoop(f"Maximum number of iterations reached ({self.max_iterations})")
        return True
    
def merge_author(bib_string:str):
    if "author" not in bib_string:return bib_string
    # Use regular expressions to find all author lines
    author_lines = re.findall(r'author = {.*?}', bib_string)

    # Extract author names from the author lines
    authors = [line.split('{')[1].split('}')[0] for line in author_lines]

    # Join the author names with 'and'
    merged_authors = ', '.join(authors)

    # Replace the author lines with the merged author line
    updated_bib_string = re.sub(r'author = {.*?}\n\s*', '', bib_string, count=len(author_lines))
    updated_bib_string = re.sub(r'author = {.*?}', f'author = {{{merged_authors}}}', updated_bib_string)
    return updated_bib_string

def multispaces_into_singlespace(text:str):
    return re.sub(r'\s+', ' ', text)

def better_latex_sentense_string(latex_string:str):
    if latex_string is None:return None
    latex_string = latex_string.replace('\n'," ")
    latex_string = multispaces_into_singlespace(latex_string)
    return latex_string.strip()

def find_last_pattern_index(s:str, pattern):
    matches = list(re.finditer(pattern, s))
    if not matches:
        return None  # or -1, if you prefer
    return matches[-1].start()


def go_ahead_and_add_label(left:str, label:str, paper_id:str):
    runtime_left = left.strip().strip("._-:").strip()
    lower_left   = runtime_left.lower() ### detect the end of the sentence is a name of ref like `In Sec:` or `In Sec.`
    ref_index    = find_last_pattern_index(lower_left, PATTERN_END_REF)
    if ref_index is not None:
        left=runtime_left[:ref_index] +' '
        label = f" [Ref.{label} of {paper_id}]"
        return left, label, True
    ref_index = find_last_pattern_index(lower_left, PATTERN_END_FIG)
    if ref_index is not None:
        left = runtime_left[:ref_index]
        label = f" [Figure.{label} of {paper_id}]"
        return left, label, True
    ref_index = find_last_pattern_index(lower_left, PATTERN_END_TAB)
    if ref_index is not None:
        left = runtime_left[:ref_index]
        label = f" [Table.{label} of {paper_id}]"
        return left, label, True
    ref_index = find_last_pattern_index(lower_left, PATTERN_END_SEC)
    if ref_index is not None:
        left = runtime_left[:ref_index]
        label = f" [Section.{label} of {paper_id}]"
        return left, label, True
    ref_index = find_last_pattern_index(lower_left, PATTERN_END_CHP)
    if ref_index is not None:
        left = runtime_left[:ref_index]
        label = f" [Chapter.{label} of {paper_id}]"
        return left, label, True
    ref_index = find_last_pattern_index(lower_left, PATTERN_END_EQU)
    if ref_index is not None:
        left = runtime_left[:ref_index]
        label = f" [Equation.{label} of {paper_id}]"
        return left, label, True
    return left, label, False

def discard_brackets(left:str, right:str):
    left= left.rstrip() if left is not None else ""
    right= right.lstrip() if right is not None else ""
    if len(left)==0:return left, right
    if len(right)==0:return left, right
    if left[-1] == "(" and right[0] == ")":
        left = left[:-1]
        right = right[1:]
    elif left[-1] == "[" and right[0] == "]":
        left = left[:-1]
        right = right[1:]
    elif left[-1] == "{" and right[0] == "}":
        left = left[:-1]
        right = right[1:]
    return left, right

def better_latex_math_code(latex_string):
    # Add a newline at the end to ensure the last comment is removed
    latex_string = latex_string.replace("\displaystyle","")
    latex_string += '\n'
    pattern = r"(?<!\\)%.*?\n"
    # Substitute each match with a newline character
    normalized_string = re.sub(pattern, '\n', latex_string)
    # Remove all newline characters
    normalized_string = normalized_string.replace('\n', ' ')
    # Remove multiple whitespace characters
    normalized_string = re.sub(r'\s+', ' ', normalized_string)
    # Remove the additional space we added at the start if it's still there
    normalized_string = normalized_string.strip()
    return normalized_string

import argparse
def print_namespace_tree(namespace, indent=0):
    namespace = vars(namespace) if not isinstance(namespace, dict) else namespace
    for key, value in namespace.items():
        print(' ' * indent, end='')
        if isinstance(value, (dict, argparse.Namespace)):
            print(key)
            print_namespace_tree(value, indent + 4)
        else:
            print(f"{key:30s} ---> {value.strip()}")


def divide_the_dict_into_two_part_by_keys(original_dict, keys_to_extract):
    part1 = {key: original_dict[key] for key in keys_to_extract if key in original_dict}
    part2 = {key: original_dict[key] for key in original_dict if key not in keys_to_extract}
    return part1, part2

def get_unique_id_from_reterive_result(pool):
    if 'unique_id' in pool:
        return pool['unique_id']
    for key in ["DOI", "ArXiv", "DBLP",'PubMed','PMID','PMC','MagID','Pii','Pmcid','ArXivId','ISBN','ISSN','PMCID']:
        _id = pool.get(f'externalids.{key}',None)
        if _id is not None:return f"{key.lower()}:{_id}"
    for key in pool.keys():
        if 'externalids' in key:raise NotImplementedError(f"what is your unique id ?? {pool}")
    ## there is not unique id, 
    
    assert 'title' in pool, f"what is your unique id ?? {pool}"
    return f"Paper:{pool['title']}"
def shrink_brackets(input_string):
    # Use a regular expression to replace all occurrences of one or more '[' with a single '['
    input_string = re.sub(r'\[+', '[', input_string)
    input_string = re.sub(r'\]+', ']', input_string)
    return input_string

def format_the_smart_citation(left, label, right, paper_id, automative_end = True):
    citation_content = label
    # Determine if label is enclosed in angle brackets and format accordingly
    if label.startswith('<') and label.endswith('>'):
        citation_content = f'[{label[1:-1]}]'
    else:
        citation_content = f'[Ref.{label} of {paper_id}]'
    
    # Determine position and format output
    is_start_of_string = not left.strip() or left.strip()[-1] in {'.', '!', '?', ';'}
    end_mark = automative_end and (not right.strip() or right.strip()[0].isupper())
    is_after_position = False
    if left and len(left.strip())>0:
        is_after_position = left.split()[-1] in prepositions
    
    if is_start_of_string or is_after_position:
        output = citation_content
    else:
        output = f'(See {citation_content})'
    
    if end_mark:
        output += '.'
    
    return output

def collect_whole_reference(labels:dict, use_count_type_ref=False):
    whole_label = {} 
    ## key_include is used for skip repeat ref use in different part of the paper, for example use 'theorems' for one section and 'theorems' for an equation. 
    ##    Notice, we only allow unique ref used for different part of the tex. In those case, it usually mean the content wont use those ref-string, therefore the tex can pass compile.
    
    for key, val_pool in labels.items():

        for type_ref_count,(k, v) in enumerate(val_pool.items()):
            #if key_include is not None and k not in key_include: continue
            if k in whole_label:
                logging.info(f"the {(k,key, v)} conflit with {(k,whole_label[k])}")
            if k not in whole_label:whole_label[k] = []
            if use_count_type_ref:
                whole_label[k].append((key,str(type_ref_count)))
            else:
                whole_label[k].append((key,v))
    return whole_label        
