from pathlib import Path
import sys
module_dir = str(Path(__file__).resolve().parent.parent)
if module_dir not in sys.path:sys.path.append(module_dir)

from upar5iv.batch_run_utils import obtain_processed_filelist, process_files,save_analysis
from upar5iv.xml_to_json.html_to_dense_text import HTMLtoJsonConfig, html_to_json_one_path_wrapper
from simple_parsing import ArgumentParser
import os

if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_arguments(HTMLtoJsonConfig, dest="config")
    args = parser.parse_args()
    args = args.config

    alread_processing_file_list = obtain_processed_filelist(args)
    results = process_files(html_to_json_one_path_wrapper, alread_processing_file_list, args)
    #print(results)
    analysis= {}
    for arxivid, _type in results:
        if _type not in analysis:
            analysis[_type] = []
        analysis[_type].append(arxivid)
    
    totally_paper_num = len(alread_processing_file_list)
    save_analysis(analysis, totally_paper_num==1, args)
