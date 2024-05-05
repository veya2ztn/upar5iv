###############
"""
Some known problem:
    - ~~See 0709.2524: The section after \appendix will not be collected into the main content. (The latexml do generate appendix, so we should fix it here)~~

"""
from bs4 import BeautifulSoup, NavigableString
from typing import Dict
from copy import deepcopy
import lxml
import logging
import os
from .check_string_is_citation import *
from .utils import *
from ..batch_run_utils import BatchModeConfig, dataclass
from tqdm.auto import tqdm
from typing import List, Dict,Tuple
from tqdm.contrib.logging import logging_redirect_tqdm

### set the loger in warning mode
log_level = os.environ.get('LOG_LEVEL', 'WARN')
logging.basicConfig(level=log_level, format='Paper ID: %(paper_id)s - %(message)s')

import traceback
enable_checkCiteDontHaveBibRef = False
enable_checkTooManyNote= True

def pretty_view(soup: BeautifulSoup):
    revert_all_the_math_to_latex(copy.deepcopy(soup))
    return soup.prettify()

def checkCiteDontHaveBibRef(string):
    if enable_checkCiteDontHaveBibRef:
        logging.info(string)
        raise CiteDontHaveBibRefError
    else:
        logging.info(string)
        return 

def checkTooManyNote(string):
    if enable_checkTooManyNote:
        logging.info(string)
        raise TooManyNoteError
    else:
        logging.info(string)
        return 

@dataclass
class HTMLtoJsonConfig(BatchModeConfig):
    task_name = 'html_to_json'
    reterive_result_mode : bool = False
    passManyNote : bool = False
    passNote : bool = False
    use_origin_ref_number : bool = False
    verbose: bool = False
    
def discard_note(soup:BeautifulSoup):
    for element in soup.find_all('ltx_note'):
        raise NotImplementedError
        remove_a_tagblock(element, 'tags')
        text = '[[[Notice: '
        append_tex = ']]] ' + (element.get_text(strip=True) or "")
        # Insert the text before the 'note' element
        element.insert_before(text)

        # Append the modified content after the 'note' element
        element.insert_after(append_tex)

        # Unwrap the 'note' element, keeping its children
        element.unwrap()
    return soup

def retrieve_all_cite(soup:BeautifulSoup):
    """
    Retrieve all the citation in the soup
        - Type 1: bib ==> <a class="ltx_ref" href="#bib.bib1" title="">1</a>
        - Type 2: fig ==> <a class="ltx_ref" href="#S2.F2" title="Figure 2 ‣ 2 THE QUADRUPOLE TRANSITION TO THE Δ⁢(1232) ‣ Probing the Structure of Nucleons in the Resonance region with CLAS at Jefferson Lab"><span class="ltx_text ltx_ref_tag">2</span></a>,
        - Type 3: tab ==> [TODO]: please give a check
        - Type 3: math==> [TODO]: please give a check
    """
    ref_count = {}
    for ref in soup.find_all(class_='ltx_ref'):
        if ref.get('href',None):
            ref_text = ref['href'].strip().lstrip('#')
            ref_count[ref_text] = ref_count.get(ref_text, 0) + 1
        elif 'ltx_ref_self' in ref.get('class',[]):
            continue
        else:
            logging.warning(f'A ref tag without href attribute ==> {ref}')
    return ref_count

def get_latex_from_math(math:BeautifulSoup):
    latex = math.get('alttext')
    if latex:return latex
    annotation = math.find('annotation-xml')
    if annotation:
        latex = annotation.text.strip()
    if latex:return latex
    latex = math.text.strip()
    if len(latex) ==0:
        logging.warning(f"it seem we find a nothing math at \n {math}")
    return latex

def identify_bibblock_is_note_or_citation(bibblock:BeautifulSoup, args:HTMLtoJsonConfig)->Tuple[bool,bool]:
    iscitationQ = True 
    hardcitationQ = False

    for ref_in_bib  in bibblock.find_all(class_='ltx_ref'):
        if ref_in_bib.get('href') and ref_in_bib.get('href').startswith('#') and len(bibblock.text.strip())>10: 
            iscitationQ = False
            hardcitationQ = True
            reason = 'has_ref'
            return iscitationQ, hardcitationQ, reason
    
        #raise NotImplementedError(f"Lets have a look ==> {bibblock}")
        
    for math_in_bib in bibblock.find_all(class_='ltx_Math'):
        latex = get_latex_from_math(math_in_bib)
        if count_activate_latex_character(latex)>15:
            logging.warning(latex + " is regard as note")
            iscitationQ = False
            hardcitationQ = True
            reason = 'has_long_math'
            return iscitationQ, hardcitationQ, reason
        #raise NotImplementedError(f"Lets have a look ==> {bibblock}")
    
    return iscitationQ, hardcitationQ, None
                
def parse_bibitem(bibitem: BeautifulSoup, 
                  bibindex:int, 
                  note_ref_labels:Dict[str, str], 
                  note_ref_metadata:Dict[str, str], 
                  bibitem_ref_labels:Dict[str, str], 
                  bibitem_ref_metadata:Dict[str, str], 
                  refcount: Dict[str, int],
                  args:HTMLtoJsonConfig):
    """
        <li id="bib.bib1" class="ltx_bibitem">
            <span class="ltx_tag ltx_tag_bibitem">[1]</span>
            <span class="ltx_bibblock"> N. Isgur and G. Karl; Phys. Lett. B72:109 (1977), Phys. Rev. D23, 817 (1981)
            </span>
        </li>
        or
        <li id="bib.bib1" class="ltx_bibitem">
            <span class="ltx_tag ltx_role_refnum ltx_tag_bibitem">[1]</span>
            <span class="ltx_bibblock">
                S. Bansal, J. Read, B. Pourbohloul, and L. A. Meyers.

            </span>
            <span class="ltx_bibblock">The dynamic nature of contact networks in infectious disease
                epidemiology.

            </span>
            <span class="ltx_bibblock"><span id="bib.bib1.1.1" class="ltx_text ltx_font_italic">J. Biol.
                    Dyn.</span>, 4:478–489, 2010.

            </span>
        </li>
    """

    #### Identify the ref_key and the tag of the bibitem
    filte_out_note = not args.passNote
    verbose = args.verbose
    tag = bibitem.find(class_='ltx_tag')
    if tag is None:
        if len(refcount)>0: logging.warning(f"empty ref ??? ==> {bibitem}")
        return ### 
    if tag is None:
        if len(refcount)>0: logging.warning(f"WARNING: the bibitem {bibitem} has no tag")
        refnum_tag = None
    else:
        refnum_tag = tag.text
    
    label_of_bib = bibitem['id']
    if not label_of_bib:
        logging.info(f" this bibitem={bibitem} dont have label ???? ")
        return
    if tag is not None: tag.decompose()
    
    #### now we will analysis whether the content of the bib is a note or citation
    #print(bibitem)

    bibitem_new = copy.deepcopy(bibitem)
    revert_all_the_math_to_latex(bibitem)
    discard_text_format_in_sentense(bibitem)
    bibblocks = bibitem_new.find_all(class_='ltx_bibblock')
    bibstring = better_latex_sentense_string(" ".join([bibblock.text for bibblock in bibblocks]))
    #assert len(bibblocks)==1, f"why this reference string ==> {bibitem} <== has more then one bibblocks ==>{bibblocks}"
    iscitationQ = True
    hardcitationQ=True
    reason = None
    if filte_out_note:
        for bibblock in bibblocks:
            iscitationQ, hardcitationQ, reason = identify_bibblock_is_note_or_citation(bibblock,args)
            break

        if iscitationQ:
            iscitationQ = not should_the_string_be_regard_as_note(bibstring)
            if not iscitationQ:reason = 'content analysis'
            if verbose and not iscitationQ:
                logging.info(f'{bibblocks} is regard as note via [string judge]')
        
    if refnum_tag is None:
        refnumtext = f"ref_{bibindex}"
    else:
        refnumtext = refnum_tag # In quant-ph_0102079: it may be <tag role="refnum"><text fontsize="90%">(40)</text></tag> like 
    
    if not iscitationQ:
        ## then, this block is a note, should save whole xml code in this block and put them into main content
        note_ref_labels[label_of_bib]  =  refnumtext
        note_ref_metadata[label_of_bib]= [hardcitationQ, deepcopy(bibitem), reason]
    else:
        #refnum_int = int(refnumtext)
        bibitem_ref_labels[label_of_bib]  = refnumtext
        bibitem_ref_metadata[label_of_bib]=bibstring

def parse_bibentry(bibitem:BeautifulSoup, bibindex:int, 
                  note_ref_labels:Dict[str, str], 
                  note_ref_metadata:Dict[str, str], 
                  bibitem_ref_labels:Dict[str, str], 
                  bibitem_ref_metadata:Dict[str, str], 
                  refcount: Dict[str, int],
                  args:HTMLtoJsonConfig):
    """
    Usually caused by directly write .bib format in .tex file. For example, arxiv: 1004.4054
    """
    raise NotImplementedError
    ### first, find the ref id
    label_of_bib = bibitem['id']
    if label_of_bib is None or len(label_of_bib.strip())==0:
        logging.info(f" this bibitem={bibitem} dont have label ???? ")
        return
    ### bibentry wont have the refnum tag, so lets use the id  
    refnumtext = label_of_bib
    
    ### if we use this, it must be a citation
    bib_origin = bibitem.find('.//default:bib-data[@role="self"]', ns)
    if bib_origin is not None:
        bib_origin.getparent().remove(bib_origin)
        # from python_script.CitationStyleLanguage import CitationStyleLanguage
        # import python_script.bibjson as bibjson
        # bibstring = " ".join(bibstring.itertext())
        # #bibstring = merge_author(bibstring)
        # bibstring = better_latex_sentense_string(bibstring)
        # bibjson_collection = bibjson.collection_from_bibtex_str(bibstring,collection='.bib')
        # if len(bibjson_collection['records']) == 0:
        #     print(bibstring)
        #     print(bibjson_collection)
        #     
        # bibpool   = bibjson_collection['records'][0]
        # citation  = CitationStyleLanguage.from_dict(bibpool)
        # bibstring = citation.to_citation(size='full')
    
    # name  = bibitem.find('.//default:bib-name', ns)
    # title = bibitem.find('.//default:bib-title', ns)
    # type  = bibitem.find('.//default:bib-type', ns)
    # date  = bibitem.find('.//default:bib-date', ns)
    # organization = bibitem.find('.//default:bib-organization', ns)
    # note  = bibitem.find('.//default:bib-note', ns)
    # publisher = bibitem.find('.//default:bib-publisher', ns)
    # volumn= bibitem.find('.//default:bib-part[@role="volume"]', ns)
    # number= bibitem.find('.//default:bib-part[@role="number"]', ns)
    # pages = bibitem.find('.//default:bib-part[@role="pages"]', ns)
    # journel= bibitem.find('.//default:bib-related[@role="host"]', ns)
    bibstring = []
    for child in bibitem:
        bibstring.append(better_latex_sentense_string(" ".join(child.itertext())))
    bibstring = ", ".join(bibstring)
        
    
    bibitem_ref_labels[labels]= refnumtext
    bibitem_ref_metadata[labels]=bibstring

def remove_entire_bibliography_and_build_labels(soup: BeautifulSoup , refcount: Dict[str, int],args:HTMLtoJsonConfig):

    bibitem_ref_labels = {}
    bibitem_ref_metadata = {}
    note_ref_labels = {}
    note_ref_metadata={}
    for bio_element in soup.find_all(class_='ltx_bibliography'):
        for bio_ul in bio_element.find_all(class_='ltx_biblist'):
            for bibindex, bio_li in enumerate(bio_ul.find_all(class_='ltx_bibitem')):
                parse_bibitem(bio_li,bibindex,note_ref_labels,note_ref_metadata, bibitem_ref_labels,bibitem_ref_metadata,refcount,args)
            for bibindex, bio_li in enumerate(bio_ul.find_all(class_='ltx_bibentry')):
                parse_bibentry(bio_li,bibindex,note_ref_labels,note_ref_metadata, bibitem_ref_labels,bibitem_ref_metadata,refcount,args)
        bio_element.decompose()
    return soup, bibitem_ref_labels, bibitem_ref_metadata, note_ref_labels, note_ref_metadata


def extract_bibblock_html_soup(bibblockli:BeautifulSoup):
    bibblocks = bibblockli.find_all('span', class_='ltx_bibblock')
    # Combine the contents of the bibblocks into a single <span class="ltx_bibblock"> element
    merged_content = []
    for bibblock in bibblocks:
        merged_content.append(" ".join([str(t).strip() for t in bibblock.contents]))
    merged_html = BeautifulSoup(f"""(Note: {' '.join(merged_content)} )""", 'html.parser')
    return merged_html

def put_note_string_back_into_each_sentence(soup: BeautifulSoup, 
                                            ref_count: Dict[str, int], 
                                            note_ref_metadata: Dict[str, Tuple[bool, BeautifulSoup]],
                                            always_put_back_note=False):
    """
    When put note back into the main content, we always think the <ref> must be in <cite>
    """
    put_back_keys  = set()
    for cite in soup.find_all(class_='ltx_cite'):
        all_refs_of_one_cite = cite.find_all(class_='ltx_ref')
        for bibref in all_refs_of_one_cite:
            #refs = bibref.get('href', "").lstrip('#').split(',') 
            ### multi_ref must be aaa,bbb,ccc, for html version there is not multi ref
            ### use "," will cause error, for example 2304.03268.html <a class="ltx_ref ltx_href" href="http://oeis.org/A080737,%20A152455" title="">A080737, A152455</a>
            #assert len(refs)==1, f"why a note ref have multi refs=>\n{bibref}"    
            #ref = refs[0].strip()
            ref = bibref.get('href', "").lstrip('#').strip()
            put_ref_backQ = False
            
            if ref in note_ref_metadata:
                put_ref_backQ = True
                hardcitationQ, bibblock, reason = note_ref_metadata[ref]
                if ref_count[ref]>2 and (not hardcitationQ) and not always_put_back_note:
                    logging.info(f"key {ref} skip, dual to many counts and its not a hardcitation")
                    continue # only when it is not type math and ref > 1 case, we dont insect note into contextf    
                #assert len(texts) == 1, f"Only single citation replacement is supported per cite element.{ref} appear more than once"
                put_back_keys = put_back_keys|set([ref])
                logging.warning(f"put back {ref} due to {reason}")
                cite.insert_before(extract_bibblock_html_soup(copy.deepcopy(bibblock)))
                bibref.decompose()
        if len(cite.find_all(class_='ltx_ref'))==0:
            cite.decompose()
        ## we then replace the entire <cite> to <bibblock> if put_ref_backQ is True
        # if put_ref_backQ:
        #     assert len(all_refs_of_one_cite)==1, f"why a cite has multi refs=>\n{cite}"
        #     cite.replace_with(bibblock)         
    return put_back_keys

def remove_figures_record_the_labels_old(soup: BeautifulSoup):
    """
        A figure example looks like
        <figure id="S2.F2" class="ltx_figure">
            <div class="ltx_flex_figure">
                <div class="ltx_flex_cell ltx_flex_size_2">
                    <figure id="S2.F2.5" class="ltx_figure ltx_figure_panel ltx_minipage ltx_align_middle" style="width:203.8pt;">
                        <img src="x1.png" id="S2.F2.1.g1" class="ltx_graphics ltx_img_square" width="239" height="239" alt="Refer to caption">
                        <figcaption class="ltx_caption">
                            <span class="ltx_tag ltx_tag_figure">Figure 1:</span>
                            Preliminary CLAS results for $R_{EM}$ of the N$\Delta(1232)$ transition. The curves represent recent models within a constituent quark model including mesons cloud effects <cite class="ltx_cite ltx_citemacro_cite">[<a href="#bib.bib12" title="" class="ltx_ref">12</a>, <a href="#bib.bib13" title="" class="ltx_ref">13</a>]</cite>, and a chiral quark soliton model <cite class="ltx_cite ltx_citemacro_cite">[<a href="#bib.bib14" title="" class="ltx_ref">14</a>]</cite>, respectively
                        </figcaption>
                    </figure>
                </div>
                <div class="ltx_flex_cell ltx_flex_size_2">
                    <figure id="S2.F2.10" class="ltx_figure ltx_figure_panel ltx_minipage ltx_align_middle" style="width:203.8pt;">
                        <img src="x2.png" id="S2.F2.6.g1" class="ltx_graphics ltx_img_square" width="239" height="239" alt="Refer to caption">
                        <figcaption class="ltx_caption">
                            <span class="ltx_tag ltx_tag_figure">Figure 2: </span>
                            Preliminary CLAS results for $R_{SM}$ of the N$\Delta(1232)$
                            transition. Same models as in Figure <a href="#S2.F2" title="Figure 2 ‣ 2 THE QUADRUPOLE TRANSITION TO THE Δ⁢(1232) ‣ Probing the Structure of Nucleons in the Resonance region with CLAS at Jefferson Lab" class="ltx_ref"><span class="ltx_text ltx_ref_tag">2</span></a>.
                        </figcaption>
                    </figure>
                </div>
            </div>
        </figure>
    """

    ### firstly, we located the deepest <figure> tag that contain the <figcaption>
    ### then, we will collect the tag (which will used in cite) and remove the whole figures 
    ## find whole the figures that has nest caption
    def is_caption_figure(tag):
        return tag.name == 'figure' and tag.find('figcaption', recursive=False) is not None
    
    primary_labels = {}
    primary_metadata = {}

    for i, caption_figure in enumerate(soup.find_all(is_caption_figure)):
        captions = caption_figure.find_all('figcaption')
        assert len(captions) == 1, f"Why this element \n{pretty_view(caption_figure)} has multiple caption??"
        caption  = captions[0]
        tags     = caption.find_all(class_='ltx_tag_figure') 
        assert len(tags) == 1, f"Why this element \n{pretty_view(caption)} has multiple tags={len(tags)}??"
        tag = tags[0].text.strip()
        tag = tag if tag else i+1

        label  = caption_figure.get('id') ## ==> S2.F2.10
        assert label is not None and len(label.strip())> 0, f"why this figure {caption_figure} has no label"
        primary_labels[label]   = tag
        primary_metadata[label] = copy.deepcopy(caption)
        
    ### then we find out whole the figure and record their figure id like
    #### - S2.F2
    #### -- S2.F2.5
    #### -- S2.F2.10
    ### this is for the case the cite will goes to the main figure rather than the subfigure
    def is_main_figure(tag):
        return (tag.name == 'figure') and ('ltx_figure' in tag.get('class', [])) and ('ltx_figure_panel' not in tag.get('class', []))
    for i, main_figure in enumerate(soup.find_all(is_main_figure)):
        main_figure.decompose()

    
    

    return primary_labels, primary_metadata

def remove_element_via_figcaption(soup: BeautifulSoup):
    """
        In 1407/1407.0389.html, you can see none of the remove_figure remove_table works due to its complicated nested structure
    """
    figcaption = soup.find('figcaption')
    
def find_tag_of_element(caption: BeautifulSoup, first_try_tag_name:str):
    tags  = caption.find_all(class_=first_try_tag_name) 
    if len(tags) == 1:
        return tags[0]
    elif len(tags) > 1:
        raise NotImplementedError(f"Why this element \n{pretty_view(caption)} has multiple tags={len(tags)}??")
    #elif len(tags) == 0:
    logging.warning(f"Why this element \n{pretty_view(caption)} has no tags={len(tags)}??")
    tags = caption.find_all(class_='ltx_tag')
    if len(tags) == 0:
        logging.warning(f"No tag found even we degenerate the mode, seem a plain image. Please check:\n{caption}")
        return None
    elif len(tags) > 1:
        raise NotImplementedError(f"Why this element \n{pretty_view(caption)} has multiple tags={len(tags)}??")
    else:
        tag = tags[0]
        logging.warning(f"Smart detected: the correct tag should be {tag}")
        return tag
        
def remove_note_and_record_the_infomration(soup: BeautifulSoup):
    primary_labels = {}
    primary_metadata = {}

    note    = soup.find(class_='ltx_note')
    counter = LoopCounter()
    while counter.increment() and note is not None:
        tag = label = f"footnote.{len(primary_labels)}"
        primary_labels[tag] = label
        primary_metadata[tag] = (True, copy.deepcopy(note))
        note.decompose()
        note = soup.find(class_='ltx_note')
    return primary_labels,primary_metadata

def remove_figures_record_the_labels(soup: BeautifulSoup):
    """
        A figure example looks like
        <figure id="S2.F2" class="ltx_figure">
            <div class="ltx_flex_figure">
                <div class="ltx_flex_cell ltx_flex_size_2">
                    <figure id="S2.F2.5" class="ltx_figure ltx_figure_panel ltx_minipage ltx_align_middle" style="width:203.8pt;">
                        <img src="x1.png" id="S2.F2.1.g1" class="ltx_graphics ltx_img_square" width="239" height="239" alt="Refer to caption">
                        <figcaption class="ltx_caption">
                            <span class="ltx_tag ltx_tag_figure">Figure 1:</span>
                            Preliminary CLAS results for $R_{EM}$ of the N$\Delta(1232)$ transition. The curves represent recent models within a constituent quark model including mesons cloud effects <cite class="ltx_cite ltx_citemacro_cite">[<a href="#bib.bib12" title="" class="ltx_ref">12</a>, <a href="#bib.bib13" title="" class="ltx_ref">13</a>]</cite>, and a chiral quark soliton model <cite class="ltx_cite ltx_citemacro_cite">[<a href="#bib.bib14" title="" class="ltx_ref">14</a>]</cite>, respectively
                        </figcaption>
                    </figure>
                </div>
                <div class="ltx_flex_cell ltx_flex_size_2">
                    <figure id="S2.F2.10" class="ltx_figure ltx_figure_panel ltx_minipage ltx_align_middle" style="width:203.8pt;">
                        <img src="x2.png" id="S2.F2.6.g1" class="ltx_graphics ltx_img_square" width="239" height="239" alt="Refer to caption">
                        <figcaption class="ltx_caption">
                            <span class="ltx_tag ltx_tag_figure">Figure 2: </span>
                            Preliminary CLAS results for $R_{SM}$ of the N$\Delta(1232)$
                            transition. Same models as in Figure <a href="#S2.F2" title="Figure 2 ‣ 2 THE QUADRUPOLE TRANSITION TO THE Δ⁢(1232) ‣ Probing the Structure of Nucleons in the Resonance region with CLAS at Jefferson Lab" class="ltx_ref"><span class="ltx_text ltx_ref_tag">2</span></a>.
                        </figcaption>
                    </figure>
                </div>
            </div>
        </figure>
    """

    ### firstly, we located the deepest <figure> tag that contain the <figcaption>
    ### then, we will collect the tag (which will used in cite) and remove the whole figures 
    ## find whole the figures that has nest caption
    
    
    def is_main_figure(tag):
        return ('ltx_figure' in tag.get('class', [])) 
    
    def is_caption_figure(tag):
        return is_main_figure(tag) and tag.find('figcaption', recursive=False) is not None

    primary_labels = {}
    primary_metadata = {}
    for main_figure in soup.find_all(is_main_figure):
        whole_captions = main_figure.find_all('figcaption')
        addtag = False
        for caption in whole_captions:
            # assert len(captions) == 1, f"Why this element {caption_figure} has multiple caption??"
            tag_obj = find_tag_of_element(caption, 'ltx_tag_figure')
            if tag_obj is not None and tag_obj.text.strip(): ### in 2106/2106.09756.html, you can find empty tag ,
                tag = tag_obj.text.strip()
                parent_of_caption = caption 
                counter = LoopCounter()
                while counter.increment() and  parent_of_caption.get('id') is None:
                    parent_of_caption = parent_of_caption.parent
                    if parent_of_caption == main_figure:break
                label  = parent_of_caption.get('id') ## ==> S2.F2.10
                assert label is not None and len(label.strip())> 0, f"why this figure {caption} has no label"
                primary_labels[label]   = tag
                primary_metadata[label] = copy.deepcopy(caption)
                addtag = True
        if len(whole_captions)==1 and main_figure.get('id') and addtag:
            label = main_figure.get('id')
            primary_labels[label]   = tag
            primary_metadata[label] = copy.deepcopy(caption)
        if len(whole_captions)==0:
            tag = label = main_figure.get('id', f"Tab.{len(primary_labels)}")
            primary_labels[label]   = tag
            primary_metadata[label] = copy.deepcopy(main_figure)
    for main_figure in soup.find_all(is_main_figure):    
        if main_figure:
            main_figure.decompose()


    
        
    ### then we find out whole the figure and record their figure id like
    #### - S2.F2
    #### -- S2.F2.5
    #### -- S2.F2.10
    ### this is for the case the cite will goes to the main figure rather than the subfigure
    
    return primary_labels, primary_metadata

def remove_floats_record_the_labels(soup: BeautifulSoup):
    """
        ## some case such as 0806/0806.1371.html use figure for tabel
    """

    def is_main_float(tag):
        return tag.name == 'float' and ('ltx_float' in tag.get('class', [])) 
    def is_figure_float(tag):
        return tag.name == 'figure' and ('ltx_float' in tag.get('class', [])) 
    primary_labels = {}
    primary_metadata = {}
    for main_floats,caption_tag in [(soup.find_all(is_main_float),'tabcaption'), (soup.find_all(is_figure_float),'figcaption')]:
        for main_float in main_floats:
            whole_captions = main_float.find_all(caption_tag)
            for caption in whole_captions:
                # assert len(captions) == 1, f"Why this element {caption_float} has multiple caption??"
                tag_obj = find_tag_of_element(caption, 'ltx_tag_float')
                if tag_obj is not None and tag_obj.text.strip():
                    tag = tag_obj.text.strip()
                    parent_of_caption = caption 
                    counter = LoopCounter()
                    while counter.increment() and  parent_of_caption.get('id') is None:
                        parent_of_caption = parent_of_caption.parent
                        if parent_of_caption == main_float:break
                    label  = parent_of_caption.get('id') ## ==> S2.F2.10
                    assert label is not None and len(label.strip())> 0, f"why this float {caption} has no label"
                else:
                    tag = label = f"Floats.{len(primary_labels)}"

                primary_labels[label]   = tag
                primary_metadata[label] = copy.deepcopy(caption)
            if len(whole_captions)==1 and main_float.get('id'):
                label = main_float.get('id')
                primary_labels[label]   = tag
                primary_metadata[label] = copy.deepcopy(caption)
            if len(whole_captions)==0:
                tag = label = main_float.get('id', f"Tab.{len(primary_labels)}")
                primary_labels[label]   = tag
                primary_metadata[label] = copy.deepcopy(main_float)

    for main_float in soup.find_all(is_main_float)+soup.find_all(is_figure_float):
        if main_float:main_float.decompose()
    return primary_labels, primary_metadata

def remove_tables_record_the_labels(soup: BeautifulSoup, strict = True):
    """
        ## some case such as cond-mat0003474.html use figure for tabel
    """

    def is_main_table(tag):
        
        if strict:
            return tag.name == 'table'  and (not strict or ('ltx_table' in tag.get('class', []) ) 
                                                        or ('ltx_tabular'in tag.get('class', [])))
        else:
            return tag.name == 'table'
    def is_figure_table(tag):
        ########## in 0505/hep-ex0505077.html, it shows another logic that represent a table/figure, lets do figcaption tracking for the remain part
        ########## 2111/2111.04522.html can see a example that no ltx_table in figure
        #return tag.name == 'figure' and (('ltx_table' in tag.get('class', [])) or (tag.find('table') is not None ) or (tag.find(class_='ltx_tabular') is not None ))
        return tag.name == 'figure' and (('ltx_table' in tag.get('class', []) ) 
                                         or (tag.find(class_='ltx_tag_table') is not None ) 
                                         or (tag.find('table') is not None ) 
                                         or (tag.find(class_='ltx_tabular') is not None )
                                         or (tag.find(class_='ltx_flex_table') is not None )
                                         )
    def is_span_table(tag):
        ########## in 1710/1710.03184.html, shows a table in <span>
        return tag.name == 'span'  and 'ltx_table' in tag.get('class', []) 
    primary_labels = {}
    primary_metadata = {}
    
    for main_tables_judger,caption_tag in [(is_main_table,'tabcaption'), 
                                           (is_figure_table,'figcaption'),
                                           (is_span_table,'ltx_caption')]:
        main_table = soup.find(main_tables_judger)
        counter = LoopCounter(len(soup.find_all(main_tables_judger))+10)
        while counter.increment() and  main_table is not None:
            whole_captions = main_table.find_all(class_=caption_tag) if caption_tag.startswith('ltx') else main_table.find_all(caption_tag)
            for caption in whole_captions:
                # assert len(captions) == 1, f"Why this element {caption_table} has multiple caption??"
                tag_obj = find_tag_of_element(caption, 'ltx_tag_table')
                if tag_obj is not None and tag_obj.text.strip():
                    tag = tag_obj.text.strip()
                    parent_of_caption = caption 
                    deepath=0
                    while parent_of_caption is not None and parent_of_caption.get('id') is None:
                        parent_of_caption = parent_of_caption.parent
                        deepath+=1
                        if deepath>5:break
                    #if parent_of_caption == main_table:break
                    label  = parent_of_caption.get('id') if parent_of_caption else None ## ==> S2.F2.10
                    assert label is not None and len(label.strip())> 0, f"why this table {caption} has no label"
                else:
                    logging.warning(f"the caption has not tag??? \n{pretty_view(caption)}")
                    tag = label = main_table.get('id', f"Tab.{len(primary_labels)}")
                    
                primary_labels[label]   = tag
                primary_metadata[label] = copy.deepcopy(caption)
            if len(whole_captions)==1 and main_table.get('id'):
                label = main_table.get('id')
                primary_labels[label]   = tag
                primary_metadata[label] = copy.deepcopy(caption)
            if len(whole_captions)==0:
                tag = label = main_table.get('id', f"Tab.{len(primary_labels)}")
                primary_labels[label]   = tag
                primary_metadata[label] = copy.deepcopy(main_table)
    
            main_table.decompose()
            main_table = soup.find(main_tables_judger)

    return primary_labels, primary_metadata

def remove_tubler_and_labels(block_equation: BeautifulSoup):
    tabular_part = block_equation.find('table', class_='ltx_tabular')
    counter = LoopCounter()
    extra_table_label   ={}
    extra_table_metadata={}
    while counter.increment() and  tabular_part is not None:
        table_label, table_metadata = remove_tables_record_the_labels(tabular_part,strict=False)
        extra_table_label=extra_table_label|table_label
        extra_table_metadata=extra_table_metadata|table_metadata
        if tabular_part:tabular_part.decompose()
        tabular_part = block_equation.find(class_='ltx_tabular')
    return extra_table_label, extra_table_metadata

def check_no_figure_and_table_left(soup:BeautifulSoup):
    
    extra_figure_label = {}
    extra_figure_metadata = {}
    # paper like 0505/astro-ph0505154.html has double tag like <figure><figure><table>xxxxxxxxx</table></figure></figure>
    for remain_figure in soup.find_all('figure'):
        if remain_figure is None:continue
        if len(remain_figure.text.strip())==0:
            remain_figure.decompose()
        else:
            raise NotImplementedError(f"why there are still figure left, what left now is \n{pretty_view(remain_figure)})")

    extra_table_label = {}
    extra_table_metadata = {}
    for remain_table in soup.find_all('table'):
        if remain_table is None:continue
        if len(remain_table.text.strip())==0:
            remain_table.decompose()
        elif remain_table.find(class_='ltx_tag'):
            revert_all_the_math_to_latex(remain_table)
            raise NotImplementedError(f"why there are still table left, what left now is \n{remain_table}")
        else:
            logging.info(f"There are still table left, seem a plain table, we store it")
            key = label = f'extra_table_{len(extra_table_label)}'
            extra_table_label[key] = label
            extra_table_metadata[key] = copy.deepcopy(remain_table)
            remain_table.decompose()
    # paper like quant-ph0003093.html will list the caption information in a table at the end of main content.
    # since it doesnt have any ref in code, we just delete the table directly
    # if len(soup.find_all('table'))>0:
    #     logging.warning(f"there are still table left, we just remove them ======> ")
    #     for table in soup.find_all('table'):
    #         if table:table.decompose()
    #assert len(soup.find_all('table'))==0, "why there are still table left"
    return extra_figure_label, extra_figure_metadata, extra_table_label,extra_table_metadata

def can_be_regard_as_math(tag:BeautifulSoup):
    return  tag.name == 'math' or 'ltx_tabular' in tag.get('class',[])

def replace_tabular_into_markdown(table:BeautifulSoup):
    rows = table.find_all('tr')
    markdown_table = []

    # Process each row
    for row in rows:
        cells = row.find_all('td')
        if not cells:
            continue
        # Extract text from each cell
        extracted_cells = [cell.get_text(strip=True) for cell in cells]
        markdown_table.append(extracted_cells)

    # Build the Markdown table
    markdown_output = ""
    headers = markdown_table[0]
    alignment_row = ["---"] * len(headers)
    
    # Create the header row
    header_row = "| " + " | ".join(headers) + " |"
    markdown_output += header_row + "\n"
    
    # Create the alignment row
    alignment_row = "| " + " | ".join(alignment_row) + " |"
    markdown_output += alignment_row + "\n"
    
    # Add the rest of the data rows
    for data_row in markdown_table[1:]:
        row = "| " + " | ".join(data_row) + " |"
        markdown_output += row + "\n"    
    table.replace_with(markdown_output)
    #return markdown_output

def revert_the_block_equation_into_latex(soup:BeautifulSoup):
    """
    Basicly, we dont need recard the tag of the equation since we will put it in the full content
        - [QUESTION] how to let mode ref back to the correct equation if it is a plain content
    
        In 1407/1407.5254.html, you may find that a table is viewed by a block equation, we have no solution for such case. 
        One possible way is entirely rewrite the ltx_tabular case via 
            \begin{align}
                xxx & xxx & xxx \\
                xxx & xxx & xxx \\
                ............... \\
                xxx & xxx & xxx \\
            \end{align}
    """
    primary_labels   = {}
    table_label= {}
    table_metadata={}
    
    # def is_block_equation(tag):
    #     return tag.name == 'table' and 'ltx_equation' in tag.get('class', []) 
    # for i, block_equation in enumerate(soup.find_all(is_block_equation)):
    block_equation = soup.find(class_='ltx_equation')
    counter = LoopCounter(len(soup.find_all(class_='ltx_equation'))+10)
    while counter.increment() and  block_equation is not None:
        tags = block_equation.find_all(class_='ltx_tag_equation')
        label= None
        tag  = None
        if len(tags) > 0:
            assert len(tags) == 1, f"Why this element \n{pretty_view(block_equation)} has multiple tags??"
            tag = tags[0]
            tag_str = tag.text.strip()
            parent  = block_equation
            deepth  = 0
            while parent is not None and not parent.get('id',None):
                parent = parent.parent
                deepth+=1
                if deepth>10:break
            label = parent.get('id',None)
            assert label is not None and len(label.strip()) > 0, f"why this equation \n{(pretty_view(block_equation))} has no label"
            primary_labels[label]   = tag_str
        
        # extra_table_label, extra_table_metadata = remove_tubler_and_labels(block_equation) #<--- lets remove the table in table no matter it is a math table
        # table_label = table_label|extra_table_label
        # table_metadata=table_metadata|extra_table_metadata
        
        whole_maths_here = block_equation.find_all('math')
        if len(whole_maths_here) == 0:
            # Currently, there exists formula with image
            if block_equation.find('img'):
                block_equation.replace_with('')
            elif block_equation.find(class_='ltx_text'):
                block_equation.replace_with(block_equation.text)
            else:
                logging.warning(f"Why this element \n{pretty_view(block_equation)} has no maths?? ")
                if tag is not None: tag.decompose()
                if block_equation.text.strip():
                    ### 1901/1901.03298.html has an example

                    logging.warning(f'this math block \n{block_equation} has text ==> {block_equation.text.strip()} <== but not math, what is it?')
                block_equation.replace_with(block_equation.text.strip())
            
        else:
            #assert len(whole_maths_here) == 1, f"Why this element {block_equation.prettify()} has multiple maths??"
            math_latex = " ".join([get_latex_from_math(math) for math in whole_maths_here])
            assert len(math_latex.strip())>0, f"why this element \n{pretty_view(block_equation)} has no maths??"
            label_string = f"id={label}" if label else ""
            block_equation.replace_with(BeautifulSoup(f"""<p class="ltx_p" {label_string}>$$\n{math_latex}\n$$\n</p>""",'html.parser').p)   
        block_equation = soup.find(class_='ltx_equation')
    return primary_labels, table_label, table_metadata


def reverse_identify_tag_and_its_label(soup,primary_labels,prefix):
    tags = soup.find_all(class_='ltx_tag')
    for tag in tags:
        parent = tag
        deepth = 0
        while parent is not None and not parent.get('id',None):
            parent = parent.parent
            deepth +=1
            if deepth>10:break
        label  = parent.get('id',None) if parent is not None else None
        if label is None:
            tag_key = label = f"{prefix}_{len(primary_labels)}"
            primary_labels[label] = tag_key
        else:
            tag_key = tag.text
            primary_labels[label] = tag_key
        


def revert_the_block_equationgroup_into_latex(soup:BeautifulSoup):
    """
    Equationgroup for format block equation like 
    <p class="ltx_p">
     $$ \phi^{AS_{a},AI_{a^{\prime}}}=  2\langle k_{A}\rangle\rho^{AS_{a}}\rho^{AI_{a^{\prime}}} \\
        \phi^{AS_{a},UI_{a^{\prime}}}= \langle k_{A}\rangle\rho^{AS_{a}}\rho^{UI_{a^{\prime}}}, \\
        \phi^{US_{a},AI_{a^{\prime}}}= \langle k_{A}\rangle\rho^{US_{a}}\rho^{AI_{a^{\prime}}}. $$
    
    """
    primary_labels   = {}

    def is_equationgroup(tag):
        return tag.name == 'table' and 'ltx_equationgroup' in tag.get('class', []) 
    ## 0505/astro-ph0505533.html shows the example that equationgroup in a span
    for  equationgroup in soup.find_all(class_='ltx_equationgroup'):
        if equationgroup.get('id',None):
            father_label = equationgroup.get('id',None)
            primary_labels[father_label]=father_label
        mathlatex_line_by_line = []
        for i,block_equation in enumerate(equationgroup.find_all(class_='ltx_eqn_row')):
            
            label= None
            #### 1305/1305.6106.html show a example that has multiple caption under one row
            # tag_obj = find_tag_of_element(block_equation, 'ltx_tag_equation')
            # if tag_obj is not None and tag_obj.text.strip():
            #     tag = tag_obj.text.strip()
            #     label  = block_equation.get('id') or equationgroup.get('id') ## ==> S2.F2.10 ==> if sub equation dont have we use its father, it usually becasue it is a single row equationgroup
            #     assert label is not None and len(label.strip()) > 0, f"why this figure {block_equation.prettify()} has no label"
            #     primary_labels[label]   = tag
            reverse_identify_tag_and_its_label(block_equation, primary_labels, 'Equation')
            ## for one <tr> row , there are mulitiple latex code 
            ## when using equation group, long math will be placed into different layout like left - right
            whole_maths_here = block_equation.find_all('math')
            if len(whole_maths_here)==0 and i==0:continue
            if len(whole_maths_here) == 0:
                if block_equation.text.strip():logging.warning(f"Why this element \n{pretty_view(block_equation)} at has no maths?? ")
            #assert len(whole_maths_here) == 1, f"Why this element {block_equation.prettify()} has multiple maths??"
            math_latex = " ".join(better_latex_math_code(get_latex_from_math(math)) for math in whole_maths_here)

            if len(block_equation.find_all(class_='ltx_tag_equation'))>0 or len(mathlatex_line_by_line)==0:
                mathlatex_line_by_line.append([   "only for debug",label, math_latex])
            else:
                mathlatex_line_by_line[-1][-1] +=r' \\ '+ math_latex
        
        mathlatex = "\n".join([f"""<p class="ltx_p" id={label}>$$\n{math_latex}\n$$\n</p>""" for tag, label, math_latex in mathlatex_line_by_line])
        newtag  = BeautifulSoup(f"<div> {mathlatex} </div>",features='html.parser')
        equationgroup.replace_with(newtag.div)
            #block_equation.replace_with(BeautifulSoup(f"""<p class="ltx_p">$$\n{math_latex}\n$$\n<p>""").p)
            #block_equation.replace_with(f"$$\n{math.get('alttext').strip()}\n$$\n")        
    return primary_labels



def revert_all_the_math_to_latex(soup:BeautifulSoup):
    for math in soup.find_all('math'):
        math.replace_with(f" ${get_latex_from_math(math)}$ ")
    return soup

def recovery_whole_citation_simple(soup: BeautifulSoup):
    """
    A typical citation 
      <cite class="ltx_cite ltx_citemacro_cite">
        <a href="#bib.bib4" title="" class="ltx_ref">fffng </a>; 
        <a href="#bib.bib1" title="" class="ltx_ref">bansal</a>
      </cite>.

    OR
        <cite class="ltx_cite ltx_citemacro_cite">[
            <a href="#bib.bib13" title="" class="ltx_ref">13</a>, 
            <a href="#bib.bib12" title="" class="ltx_ref">12</a>]
        </cite>.
    """
    for cite in soup.find_all(class_='ltx_citemacro_cite'):
        for ref in cite.find_all(class_='ltx_ref'):
            ref = cite.find(class_='ltx_ref')
            ref.replace_with(f"[{ref.text}]")
        cite.replace_with(f" {shrink_brackets(cite.text.replace('],[', ','))}")

    for ref in soup.find_all(class_='ltx_ref'):
        ref.replace_with(f" {ref.text}")        

def beautify_sentence(soup: BeautifulSoup):
    for p in soup.find_all('p'):
        new_content = []
        for element in p.contents:
            if isinstance(element, NavigableString):
                new_content.append(better_latex_sentense_string(str(element)))
            else:
                new_content.append(str(element))
        p.clear()
        p.append(' '.join(new_content))

def beautify_section_title(soup: BeautifulSoup):
    for level in [1,2,3,4,5,6,7]:
        for h in soup.find_all(f'h{level}'):
            h.replace_with("\n"+"#"*level+f" {better_latex_sentense_string(h.text)}")
            
def deal_with_itermize(soup):
    for ul in soup.find_all('ul',class_='ltx_itemize'):
        for li in ul.find_all('li'):
            li.replace_with("- "+f"{better_latex_sentense_string(li.text)}")
            
def discard_para(soup):
    for div in soup.find_all('div',class_='ltx_para'):
        div.replace_with(f"\n{div.text.strip()}\n")
        
def discard_section(soup: BeautifulSoup):
    for section in soup.find_all('section',class_='ltx_section'):
        section.replace_with(f"{section.text.strip()}")

def discard_text_format_in_sentense(soup: BeautifulSoup, cleanmode=False):
    def is_italic(tag):
        return tag.name == 'span' and 'ltx_text' in tag.get('class', []) and 'ltx_font_italic' in tag.get('class', [])
    for italic_text in soup.find_all(is_italic):
        if cleanmode:
            italic_text.replace_with(f"{better_latex_sentense_string(italic_text.text.strip('*'))}")
        else:
            italic_text.replace_with(f"*{better_latex_sentense_string(italic_text.text.strip('*'))}*")
    def is_bold(tag):
        return tag.name == 'span' and 'ltx_text' in tag.get('class', []) and 'ltx_font_bold' in tag.get('class', [])
    for bold_text in soup.find_all(is_bold):
        if cleanmode:
            bold_text.replace_with(f"{better_latex_sentense_string(bold_text.text.strip('*'))}")
        else:
            bold_text.replace_with(f"**{better_latex_sentense_string(bold_text.text.strip('*'))}**")
    for text in soup.find_all(class_='ltx_text'):
        text.replace_with(better_latex_sentense_string(text.text or ""))
   
def remove_and_collect(soup: BeautifulSoup, name):
    if soup is None:return 
    element = soup.find(class_=name)
    if element:
        obj = copy.deepcopy(element)
        element.decompose()
        return obj

def remove_and_collect_abstract(soup: BeautifulSoup):
    abstract = soup.find(class_='ltx_abstract')
    if abstract:
        obj = copy.deepcopy(abstract)
        abstract.decompose()
        return obj

def collect_specific_section_and_remove(soup, name='ltx_appendix'):
    whole_sections = []
    for section in soup.find_all(class_=name):
        whole_sections.append(section_to_json(section))
        section.decompose()
    return whole_sections
    


def collect_sections_to_content_old(soup):
    def is_other_section(tag):
        return tag.name == 'section' and 'ltx_subsection' not in tag.get('class',[]) and 'ltx_subsubsection' not in tag.get('class',[]) 
    whole_normal_sections = soup.find_all(class_='ltx_section')
    if len(whole_normal_sections) == 0:
        logging.info(f'this html doesnt have ltx_section, thus we use whole para directly, make sure no appendix in')
        assert len(soup.find_all(is_other_section)) ==0, f"why the html wont have ltx section but have another section type, please check"
        whole_normal_sections = [soup]
    whole_sections = []
    for section in whole_normal_sections:
        whole_sections.append(section_to_json(section))
    return whole_sections

def is_content_content(tag):
        return (tag.name == 'section' and any([t in tag.get('class',[]) for t in ['ltx_chapter', 'ltx_section', 
                                                                                  'ltx_subsection', 'ltx_subsubsection', 
                                                                                  'ltx_paragraph','ltx_glossary','ltx_slide']])
            or  tag.name == 'div' and any([t in tag.get('class',[]) for t in ['ltx_para']])
            or  tag.name == 'p' or tag.name == 'ul'
                )

def collect_sections_to_content(soup):
    """
        Version Beta: 
            Lets just scan the soup level by level, possible top level 
            - <section class='ltx_section'>
            - <section class='ltx_subsection'>
            - <section class='ltx_subsubsection'>
            - <section class="ltx_paragraph">
            - <div class="ltx_para">
            
    """
    section = {'title': None, 'content' : []}
    title = soup.find(class_='ltx_title',recurive=False)
    if title: section['title']= better_latex_sentense_string(title.text)
    contetn_section = soup.find(is_content_content)
    counter = LoopCounter(len(soup.find_all(is_content_content))+10)
    while counter.increment() and  contetn_section is not None:
        if contetn_section.name in ['p', 'ul']:
            section['content'].append(better_latex_sentense_string(contetn_section.text))
        else:
            section['content'].append(collect_sections_to_content(copy.deepcopy(contetn_section)))
        contetn_section.decompose()
        contetn_section = soup.find(is_content_content)
    
    return section


def section_to_json(soup):
    '''
    <h2 class="ltx_title ltx_title_section"> 
        <span class="ltx_tag  ltx_tag_section"> 1 </span> INTRODUCTION 
    </h2>
    <div class="ltx_para" id="S1.p1">
    </div>
    '''
    section = {'title': None, 'paragraph' : []}
    title = soup.find(class_='ltx_title_section')
    if title: section['title']= better_latex_sentense_string(title.text)
    for para in soup.find_all(class_='ltx_para'):
        section['paragraph'].append(para_to_json(para))
    return section

def para_to_json(soup):
    sentenses = []
    for p in soup.find_all(['p','ul']):
        sentenses.append(better_latex_sentense_string(p.text))
    return sentenses

def collect_abstract(soup):
    if soup is None:return
    revert_the_block_equation_into_latex(soup)
    revert_all_the_math_to_latex(soup)
    recovery_whole_citation_simple(soup)
    discard_text_format_in_sentense(soup)
    beautify_sentence(soup)
    
    content = []
    for p in soup.find_all('p'):
        content.append(p.text)
    return "\n".join(content)

def collect_author(soup):
    """
    We only take the name 
    <div class="ltx_authors">
        <span class="ltx_creator ltx_role_author">
        <span class="ltx_personname">Chao-Ran Cai </span>
        <span class="ltx_author_notes">
        <span class="ltx_contact ltx_role_affiliation">School of Physics, Northwest University,Xi’an 710127, China</span>
        <span class="ltx_contact ltx_role_affiliation">Shaanxi Key Laboratory for Theoretical Physics Frontiers, Xi’an 710127, China </span></span></span>
        <span class="ltx_author_before"></span><span class="ltx_creator ltx_role_author">
        <span class="ltx_personname">Yuan-Yuan Nie </span><span class="ltx_author_notes">
        <span class="ltx_contact ltx_role_affiliation">School of Physics, Northwest University, Xi’an 710127, China </span></span></span>
        <span class="ltx_author_before"></span><span class="ltx_creator ltx_role_author">
        <span class="ltx_personname">Petter Holme </span><span class="ltx_author_notes">
        <span class="ltx_contact ltx_role_email"><a href="mailto:petter.holme@aalto.fi">petter.holme@aalto.fi</a> </span>
        <span class="ltx_contact ltx_role_affiliation">Department of Computer Science, Aalto University, Espoo, Finland </span>
        <span class="ltx_contact ltx_role_affiliation">Center for Computational Social Science, Kobe University, Kobe, Japan </span></span></span>
    </div>
    """
    if soup is None: return
    revert_all_the_math_to_latex(soup)
    authors = []
    for author_name in soup.find_all(class_='ltx_personname'):
        authors.append(better_latex_sentense_string(author_name.text))
    return authors

def collect_acknowledgements(soup):
    """
    <div class="ltx_acknowledgements">
        <h6 class="ltx_title ltx_title_acknowledgements">Acknowledgements.</h6>
        This work was supported by the Shaanxi Fundamental Science Research Project for Mathematics and
        Physics (Grant No. 22JSQ003). PH was supported by JSPS KAKENHI Grant Number JP 21H04595.
    <div>
    
    """
    if soup is None: return
    ### remove the title
    for title in soup.find_all(class_='ltx_title'):title.decompose()
    revert_all_the_math_to_latex(soup)
    return better_latex_sentense_string(soup.text)

def simple_cleanup_html(soup):
    revert_all_the_math_to_latex(soup)
    discard_text_format_in_sentense(soup)
    beautify_sentence(soup)
    deal_with_itermize(soup)

def cleanup_html(soup, whole_ref_to_labels,paper_id,refs_that_wont_recovery=[]):
    revert_the_block_equationgroup_into_latex(soup)
    revert_the_block_equation_into_latex(soup)
    #recovery_whole_citation_simple(soup)
    recovery_whole_citation_complete(soup,whole_ref_to_labels, paper_id,refs_that_wont_recovery)
    revert_all_the_math_to_latex(soup)
    discard_text_format_in_sentense(soup)
    beautify_sentence(soup)
    deal_with_itermize(soup)
    #beautify_section_title(soup)
    #tree = replace_item_block_with_markdown_format(tree)

def cleanup_reference_string(soup, whole_ref_to_labels,paper_id, refs_that_wont_recovery):
    cleanup_html(soup, whole_ref_to_labels, paper_id, refs_that_wont_recovery = refs_that_wont_recovery)
    string = soup.text.replace("[[[Notice:","").replace("]]]","")
    return better_latex_sentense_string(string)

def recovery_citation_in_sentense(cite: BeautifulSoup, labels_reference: Dict[str, str], paper_id: str, refs_that_wont_recovery=[]):
    plain_ref = []
    refs = []
    for ref in cite.find_all(class_='ltx_ref'):
        ref_key = ref.get('href',"")
        if ref_key:
            refs.append(ref_key.strip().lstrip('#'))
        else:
            logging.warning(f"this ref has no href:\n{ref}")
            if len(ref.text.strip())>0:
                plain_ref.append(ref.text.strip())
                ref.replace_with(ref.text.strip())
            else:
                raise NotImplementedError(f"Please check why this ref has no href:\n{ref}")
            
    refs = [ref for ref in refs if ref not in refs_that_wont_recovery]
    if len(plain_ref)>0:
        if len(refs)>0: 
            ### 1609/1609.07311.html is an example that both have ref and linked ref .
            logging.warning(f"Normally one citation either has plain ref or linked ref,see \n{pretty_view(cite)}")
        else:
            cite.replace_with(" ".join(plain_ref))
            return
    
    label_list = []
    for ref in refs:
        reflabels = labels_reference[ref]
        if len(reflabels) > 1:
            logging.info(f"multiple label detected: {reflabels}, we will use the first one")
        ref_type, label = reflabels[0]
        label_list.append(label.strip("[](){}"))
    if len(label_list) ==0:
        cite.decompose()
        return 
    
    label = ",".join(label_list)    
    label = "[" + label + "]"
    next_string = cite.next_sibling 
    prev_string = cite.previous_sibling
    
    right       = next_string.strip() if next_string and isinstance(next_string,NavigableString) else ""
    left        = prev_string.strip() if prev_string and isinstance(prev_string,NavigableString) else ""
    left, right = discard_brackets(left,right)
    
    #leftbrace   = "" if left and left.strip()[-1] in ['[','(','{']  else "["
    #rightbrace  = "" if right and right.strip()[0] in [']',')','}'] else "]"
    #label = leftbrace + label + rightbrace
    isactivated = False
    if left:
        left, label, isactivated = go_ahead_and_add_label(left, label, paper_id)      
    else:
        left = ""
    label = format_the_smart_citation(left, label, right, paper_id, automative_end = isinstance(next_string,NavigableString))
    # print(f"""{left} |||||| {label} |||||| {right}""")
    # print("==============================")
    if prev_string and isinstance(next_string,NavigableString):prev_string.replace_with(NavigableString(left))
    cite.replace_with(label)
    if next_string and isinstance(prev_string,NavigableString):next_string.replace_with(NavigableString(right))

    #new_tag = BeautifulSoup(f"<span>{label}</span>", 'html.parser').span

def recovery_ref_in_sentense(ref: BeautifulSoup, labels_reference: Dict[str, str], paper_id: str,refs_that_wont_recovery=[]):
    ref_key = ref.get('href', None)
    if not ref_key:
        if 'ltx_ref_self' in ref.get('class',[]):
            ref.decompose()
        else:
            logging.warning(f"""ref of element dont have ref??? See {ref.prettify()}""")
            ref.replace_with(ref.text)
        #raise
        return
    ref_key = ref_key.strip().lstrip('#')
    if ref_key not in labels_reference:
        logging.warning(f"""{ref_key} not in labels_reference, please check.""")
        #ref.replace_with(f" {ref.text}")       #Degenerate to simple mode  
        raise NotImplementedError("MUST raise here, as it will go infinity loop")
        return
    
    reflabels = labels_reference[ref_key]
    if len(reflabels) > 1:
        reflabels = [[a,b] for a,b in reflabels if a not in ['Ref']]  ## The Ref from ltx_tag_ref which is quite normal and cause problem see 1511/1511.06005.html
    if len(reflabels) > 1:
        raise NotImplementedError(f'multiple label detected for {ref_key} => {reflabels}, we will use the first one')
    
    ref_type, label = reflabels[0]
    next_string = ref.next_sibling 
    prev_string = ref.previous_sibling
    
    right       = next_string.strip() if next_string and isinstance(next_string,NavigableString) else ""
    left        = prev_string.strip() if prev_string and isinstance(prev_string,NavigableString) else ""
    left, right = discard_brackets(left,right)
    
    # if left:
    #     left, label, isactivated = go_ahead_and_add_label(left, label, paper_id)      
    # else:
    #     left = ""
    # if not isactivated:
    #     if ref_type.lower() in ['url']:
    #         label = label
    #     elif ref_type.lower() not in ['equation','formula']:
    #         label = f" (See [{ref_type}.{label} of {paper_id}]) "
    #     else:
    #         label = f"[{ref_type}.{label} of {paper_id}]"
    # ref.replace_with(label)
    isactivated = False
    if left:
        left, label_new, isactivated = go_ahead_and_add_label(left, label, paper_id)      
    else:
        left = ""
    if not isactivated:
        if ref_type.lower() in ['url']:
            label = label
        elif ref_type.lower() not in ['equation', 'formula']:
            label = f" (See [{ref_type}.{label} of {paper_id}]) "
        else:
            label = f"[{ref_type}.{label} of {paper_id}]"    
    else:
        label = label_new

    if prev_string and isinstance(next_string,NavigableString):prev_string.replace_with(NavigableString(left))
    ref.replace_with(label)
    if next_string and isinstance(prev_string,NavigableString):next_string.replace_with(NavigableString(right))

def recovery_whole_citation_complete(soup: BeautifulSoup,whole_ref_to_labels, paper_id,refs_that_wont_recovery=[]):
    """
        firstly deal with <ref> in <cite>
        then deal with <ref> for figure. math. table, and so on

        ## you must use a counter = LoopCounter()
    while counter.increment() and  loop since the sibling information may changed, try [cond-mat0003294.html]
        ## the for loop will get failed when continues <cite> tag such as 
        <cite class="ltx_cite ltx_citemacro_cite">[<a href="#bib.bib1" title="" class="ltx_ref">1</a>]</cite><cite class="ltx_cite ltx_citemacro_cite">[<a href="#bib.bib2" title="" class="ltx_ref">2</a>]</cite><cite class="ltx_cite ltx_citemacro_cite">[<a href="#bib.bib3" title="" class="ltx_ref">3</a>]</cite>.
    """
    #for cite in soup.find_all(class_='ltx_citemacro_cite'): 
    cite = soup.find(class_='ltx_citemacro_cite')
    counter = LoopCounter(max_iterations=len(soup.find_all(class_='ltx_citemacro_cite'))+10)
    while counter.increment() and  cite is not None:
        recovery_citation_in_sentense(cite, whole_ref_to_labels, paper_id,refs_that_wont_recovery=refs_that_wont_recovery)
        cite = soup.find(class_='ltx_citemacro_cite')
    # for ref in soup.find_all(class_='ltx_ref'):
    ref = soup.find(class_='ltx_ref')
    counter = LoopCounter(max_iterations=len(soup.find_all(class_='ltx_ref'))+10)
    while counter.increment() and  ref is not None :
        recovery_ref_in_sentense(ref, whole_ref_to_labels, paper_id,refs_that_wont_recovery=refs_that_wont_recovery)
        ref = soup.find(class_='ltx_ref')

def collect_tags_and_record_all_labels(soup: BeautifulSoup):
    ### please make sure you remove the figure, table, equation 
    otherslabels={}
    for tag in soup.find_all(class_='ltx_tag'):
        label_type = [_type for _type in tag.get('class', []) if _type.startswith('ltx_tag_')]
        if len(label_type)>0:
            assert len(label_type)==1
            label_type = label_type[0].replace('ltx_tag_','').capitalize()
        else:
            label_type = 'Other'
        if label_type not in otherslabels:otherslabels[label_type]={}
        parent = tag

        deepth = 0
        while parent is not None and not parent.get('id',None):
            parent = parent.parent
            deepth +=1
            if deepth>10:break
        
        label = parent.get('id',None) if parent is not None else None
        if label:
            otherslabels[label_type][label.strip()] = tag.text.strip()
    return otherslabels

def count_activate_latex_character(latex_string):
    # Split the string to separate components, keeping LaTeX commands and handling escaped spaces
    components = re.split(r'(?<!\\) ', latex_string)
    
    # Define a regex pattern to count effective characters:
    # This pattern matches:
    # - LaTeX commands possibly with arguments enclosed in curly braces
    # - Single alphanumeric characters possibly followed by subscript or superscript
    # - Individual arithmetic operators
    pattern = r'\\[a-zA-Z]+\{[^}]*\}|\\[a-zA-Z]+|\w(?:_{[^}]*}|\^{[^}]*})?|[\w+-/*]'
    
    effective_count = 0
    for component in components:
        # Remove extra backslashes used for escaping in the split step
        component = component.replace('\\ ', ' ')
        # Find all matches that count as "effective characters"
        matches = re.findall(pattern, component)
        effective_count += len(matches)

    return effective_count
import logging



class ContextFilter(logging.Filter):
    def __init__(self, paper_id):
        super().__init__()
        self.paper_id = paper_id

    def filter(self, record):
        record.paper_id = self.paper_id
        return True
import json
def deal_with_html_file(tmp_html_path, output_dir, args:HTMLtoJsonConfig)->str:
    

    use_count_type_ref  = not args.use_origin_ref_number
    reterive_result_mode=args.reterive_result_mode
    _paper_id =os.path.basename(tmp_html_path.replace('.html',''))
    paper_filter = ContextFilter(_paper_id)
    logging.getLogger().addFilter(paper_filter)
    logging_redirect_tqdm()
    paper_id = f"ArXiv.{_paper_id}"
    soup_whole = BeautifulSoup(open(tmp_html_path),'html.parser')
    soup = soup_whole.find('article')
    if not soup: return 'NoArticle'
    ReferenceDir= os.path.join(output_dir, "Reference")
    author  = remove_and_collect(soup, 'ltx_authors')
    abstract= remove_and_collect(soup, 'ltx_abstract')
    acknowledgements= remove_and_collect(soup, 'ltx_acknowledgements')



    discard_note(soup)
    ref_count = retrieve_all_cite(soup)
    new_soup = deepcopy(soup)
    new_soup,reference_labels,bibitem_ref_metadata,note_ref_labels, note_ref_metadata= remove_entire_bibliography_and_build_labels(new_soup,ref_count, args)
    if len(note_ref_metadata)>5:
        for key,val in note_ref_metadata.items():
            logging.info(f"{key} ==> [ {better_latex_sentense_string(' '.join(val[1].text))} ]")
        checkTooManyNote(f'the note_ref_metadata num={len(note_ref_metadata) } is too much , please check the file {tmp_html_path}')
        logging.warning('WARNING:Too Many note, we roll back to no note mode')
        args.passNote = True
        soup,reference_labels,bibitem_ref_metadata,note_ref_labels, note_ref_metadata= remove_entire_bibliography_and_build_labels(soup,ref_count,args)
    else:
        soup= new_soup

    reference_labels, reference_labels_not_in_context = divide_the_dict_into_two_part_by_keys(reference_labels, ref_count)
    note_ref_labels, note_ref_labels_not_in_context = divide_the_dict_into_two_part_by_keys(note_ref_labels,ref_count)
    bibitem_ref_metadata, bibitem_ref_metadata_not_in_context = divide_the_dict_into_two_part_by_keys(bibitem_ref_metadata,ref_count)
    note_ref_metadata, note_ref_metadata_not_in_context = divide_the_dict_into_two_part_by_keys(note_ref_metadata,ref_count)

    footnote_labels, footnote_metadata = remove_note_and_record_the_infomration(soup)
    note_ref_labels=note_ref_labels|footnote_labels
    note_ref_metadata=note_ref_metadata|footnote_metadata

    put_back_keys = put_note_string_back_into_each_sentence(soup,ref_count,note_ref_metadata)
    ## since we put those key back into content, we never need those key anymore and wont save them in the reference.txt
    for key in put_back_keys:
        del note_ref_labels[key]
        del note_ref_metadata[key]
    # notice, after this line, the key in note_ref_metadata and note_ref_labels is different
    
    figures_labels, figures_metadata = remove_figures_record_the_labels(soup)
    tables_labels, tables_metadata   = remove_tables_record_the_labels(soup)
    floats_labels, floats_metadata   = remove_floats_record_the_labels(soup)
    equation_group_labels =revert_the_block_equationgroup_into_latex(soup)
    equation_labels,extra_table_label, extra_table_metadata      =revert_the_block_equation_into_latex(soup)
    tables_labels = tables_labels|extra_table_label
    tables_metadata=tables_metadata|extra_table_metadata
    in_content_ref_labels = {
        'Figure':figures_labels,
        'Table':tables_labels,
        'Equation':equation_labels,
        'Equationgroup':equation_group_labels,
        'Floats':floats_labels
    }
    labels               = collect_tags_and_record_all_labels(soup)## like section and so one
    extra_figure_label, extra_figure_metadata, extra_table_label,extra_table_metadata = check_no_figure_and_table_left(soup)
    assert len(set(in_content_ref_labels)&set(labels))==0, f"the remain tag should not include those collect before. \n collect before:{in_content_ref_labels.keys()}\n now:{labels.keys()}"
    figures_labels   =   figures_labels | extra_figure_label
    figures_metadata = figures_metadata | extra_figure_metadata
    tables_labels    = tables_labels    | extra_table_label
    tables_metadata  =  tables_metadata | extra_table_metadata
    
    all_citation_keys = set(ref_count)
    all_reference_keys= (set(reference_labels)|
                         set(note_ref_labels)|
                         set(figures_labels)|
                         set(tables_labels)|
                         set(equation_labels)|
                         set(equation_group_labels)|
                         set(equation_group_labels)|
                         set(floats_labels))

    for val_pool in labels.values():
        all_reference_keys = all_reference_keys | set(val_pool)
    missing_citation = all_citation_keys - all_reference_keys
    missing_citation_labels = {missing_citation_label:f'MissingCite_{i}' for i,missing_citation_label in enumerate(missing_citation)}

    
    #assert len(bibitem_ref_metadata)>0, f"Error: this file [{tmp_xml_path}] donts have bib???"
    
    if reterive_result_mode:
        assert os.path.exists(os.path.join(ReferenceDir,'reference.keys.done'))
        assert os.path.getsize(os.path.join(ReferenceDir,'reference.txt')) == 0, "if you want to inject the reterive result, please make sure all the element is reterived"
        with open(os.path.join(ReferenceDir,'reference.keys.done'),'r') as f:
            reference_keys = [t.strip() for t in f]
        with open(os.path.join(ReferenceDir,'reference.es_retrived_citation.json.done'),'r') as f:
            reference_reterives = json.load(f)
        assert len(reference_keys) == len(reference_reterives), "the reterive result should have the same length as the keys"
        new_label_mapping = {}
        for key, reterive_result in zip(reference_keys,reference_reterives):
            if key not in new_label_mapping:new_label_mapping[key] = []
            new_label_mapping[key].append(get_unique_id_from_reterive_result(reterive_result))
        for key in new_label_mapping.keys():
            new_label_mapping[key] = "<"+ ",".join(new_label_mapping[key]) + ">"
        reference_labels = new_label_mapping


    whole_ref_to_labels = collect_whole_reference(in_content_ref_labels|
                                                  {'Reference':reference_labels,'Missing':missing_citation_labels}|
                                                  labels, 
                                                  use_count_type_ref=use_count_type_ref)

    lack_ref = list(set(ref_count) - (set(all_reference_keys)|set(whole_ref_to_labels)))
    if len(lack_ref)>0:
        logging.info(f'you have {len(lack_ref)} ref lacks, such as {lack_ref[:4]}, please check the file {tmp_html_path}')
        raise MisMatchRefError
    
    ## now, the left note metadata is those string looks like a citation, and we will put them back into the bibitem information
    for remain_key, remain_val in note_ref_metadata.items():
        
        reference_labels[remain_key]=note_ref_labels[remain_key]
        string = cleanup_reference_string(remain_val[1], whole_ref_to_labels,paper_id, refs_that_wont_recovery=put_back_keys)
        bibitem_ref_metadata[remain_key]=better_latex_sentense_string(string)

    
    whole_ref_to_labels = collect_whole_reference(in_content_ref_labels|
                                                  {'Reference':reference_labels,'Missing':missing_citation_labels}|
                                                  labels, 
                                                  use_count_type_ref=use_count_type_ref)

    cleanup_html(soup, whole_ref_to_labels,paper_id,refs_that_wont_recovery=[])


    for remain_key, remain_val in note_ref_metadata_not_in_context.items():
            string = cleanup_reference_string(remain_val[1], whole_ref_to_labels,paper_id, refs_that_wont_recovery=put_back_keys)
            note_ref_metadata_not_in_context[remain_key]=better_latex_sentense_string(string)
            ## do this again since we modify the bibitem_ref_metadata
    
    for metadatapool in [figures_metadata, tables_metadata, floats_metadata]:
        for remain_key, remain_val in metadatapool.items():
            string = cleanup_reference_string(remain_val, whole_ref_to_labels,paper_id, refs_that_wont_recovery=put_back_keys)
            metadatapool[remain_key]=better_latex_sentense_string(string)

    
    whole_metadata = {'figures_metadata':figures_metadata,
                      'tables_metadata':tables_metadata,
                      'floats_metadata':floats_metadata,
                      'bibitem_ref_metadata':bibitem_ref_metadata,}
        
    content_soup = copy.deepcopy(soup)
    appendix_content = collect_specific_section_and_remove(content_soup,name=['ltx_appendix','ltx_part'])
    index_content    =  collect_specific_section_and_remove(content_soup,name='ltx_index')
    sections_content = collect_sections_to_content(content_soup)
    assert len(content_soup.find_all('section')) ==0, f"why the html wont have ltx section but have another section type, please check"
    output_dict = {'abstract':collect_abstract(abstract),
                   'acknowledge':collect_acknowledgements(acknowledgements),
                   'author': collect_author(author),
                   'appendix':appendix_content,
                   'sections':sections_content,
                   'index':index_content,
                   'metadata':whole_metadata,
                   'paper_id':paper_id,
                   'whole_ref_to_labels':whole_ref_to_labels,
                   'missing_citation_labels':missing_citation_labels}
    os.makedirs(output_dir, exist_ok=True)
    ReferenceDir= os.path.join(output_dir, "Reference")
    os.makedirs(ReferenceDir, exist_ok=True)
    Content_Path = os.path.join(output_dir, f'{_paper_id}.retrieved.json') if reterive_result_mode else os.path.join(output_dir, f'{_paper_id}.json')
    with open(Content_Path, 'w') as f:json.dump(output_dict, f, indent=2)
    
    
    #logging.info(Content_Path)
    if not reterive_result_mode:
        keys  = list(bibitem_ref_metadata.keys())
        citation_string = [bibitem_ref_metadata[key] for key in keys]

        with open(os.path.join(ReferenceDir, f'reference.keys'), 'w') as f:
            for key in keys:f.write(key+'\n')
        with open(os.path.join(ReferenceDir, f'reference.txt'), 'w') as f:
            for string in citation_string:f.write(string+'\n')
        with open(os.path.join(ReferenceDir, f'bibitem_ref_metadata_not_in_context.json'), 'w') as f:
            json.dump(bibitem_ref_metadata_not_in_context, f, indent=2)
        with open(os.path.join(ReferenceDir, f'note_ref_metadata_not_in_context.json'), 'w') as f:
            json.dump(note_ref_metadata_not_in_context, f, indent=2)
    
        # for section in collect_whole_section_into_one_paper(tree):
        #     logging.info(f"=========> {section['section_title']} <============")
        #     for paragraph in section['section_content']:
        #         logging.info("=======================")
        #         for sentense in paragraph:
        #             logging.info(sentense)
    return 'Finish'

def html_to_json_one_path(file_path, args:HTMLtoJsonConfig)->Tuple[str,str]:
    file_path = file_path.strip()
    arxivid   = os.path.basename(file_path.replace('.html',''))
    arxivid_parent = os.path.basename(os.path.dirname(file_path))
    if not os.path.exists(file_path):
        return file_path, 'NoHTML'
    if args.savepath:
        output_root = os.path.join(args.savepath,arxivid_parent,arxivid)
    else:
        output_root = os.path.dirname(file_path)
    
    
    output_dir  = os.path.join(output_root, 'upar5iv')
    target_file = os.path.join(output_dir, arxivid+'.json')
    if os.path.exists(target_file) and not args.redo:
        return arxivid, 'Skip'
    try:
        code = deal_with_html_file(file_path, output_dir, args)
        return arxivid,code
    except KeyboardInterrupt:
        raise
    except MathDontHaveTex:
        logging.info(f"MathDontHaveTex ===> {file_path}")
        return arxivid,'MathDontHaveTex'
    except lxml.etree.XMLSyntaxError:
        logging.info(f"bad xml file ===> {file_path}")
        if args.verbose:traceback.print_exc()
        return arxivid,'badxml'
    except TooManyNoteError:
        #logging.info(f"too many note ===> {file_path}")
        #analysis['TooManyNoteError'].append(file_path)
        return arxivid,'TooManyNoteError'
    except CiteDontHaveBibRefError:
        #logging.info(f"cite dont have bibref ===> {file_path}")
        #analysis['CiteDontHaveBibRefError'].append(file_path)
        return arxivid,'CiteDontHaveBibRefError'
    except MisMatchRefError:
        #logging.info(f"mismatch ref ===> {file_path}")
        #analysis['MisMatchRefError'].append(file_path)
        return arxivid,'MisMatchRefError'
    except:
        
        if args.verbose == 1:
            traceback.print_exc()
        #tqdm.write(f"fail ===> {file_path}")
        if args.debug:
            logging.error(f"fail ===> {file_path}")
            raise
        return file_path,'Fail'
    
def html_to_json_one_path_wrapper(args):
    arxiv_path, args = args
    
    return html_to_json_one_path(arxiv_path, args)

"""
/nvme/zhangtianning/datasets/ar5iv/no-problem/0003/hep-ph0003189.html <=== footnote
<span class=\"ltx_note ltx_role_footnote\" id=\"footnote2\"><sup class=\"ltx_note_mark\">\u2020</sup><span class=\"ltx_note_outer\"><span class=\"ltx_note_content\"><sup class=\"ltx_note_mark\">\u2020</sup><span class=\"ltx_tag ltx_tag_note\">\u2020</span>Note that in the literature an alternative definition is also used which differs from our definition in [Equation.1 of ArXiv.hep-ph0003189] by an approximate factor of 2.</span></span></span>
"""