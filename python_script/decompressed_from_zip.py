import os
import zipfile
from multiprocessing import Pool
from tqdm.auto import tqdm
from multiprocessing import Pool, cpu_count, Manager
"""
run `unzip -l xxxxx.zip > filelist.txt` to get the filelist
"""

def extract_file(args):
    """Extract a single file if it does not already exist in the destination folder."""
    filename, fileroot = args
    destination_path = os.path.join('./', filename)
    if not os.path.exists(destination_path):
        with zipfile.ZipFile(fileroot, 'r') as zip_ref:
            zip_ref.extract(filename, './')
        pass
        #with lock:tqdm.write(f"Extracted: {filename}")
    else:
        pass
        #with lock:tqdm.write(f"Skipped (exists): {filename}")

def batch_extract(files_to_extract,fileroot='ar5iv-04-2024-warnings.zip',index_part=0):
    wrapped_files = [(file, fileroot) for file in files_to_extract]
    # Use a pool of workers equal to the number of available CPU cores
    with open(f'log/convert/thread.{index_part}.log', 'w') as f:
        with Pool(processes=int(cpu_count()/1.2)) as pool:
            # Using starmap to pass multiple arguments
            list(tqdm(pool.imap(extract_file, wrapped_files), total=len(wrapped_files), file=f))

if __name__ == '__main__':

    import os
    import sys
    from tqdm.auto import tqdm
    import numpy as np
    import traceback
    import argparse, logging
    parser = argparse.ArgumentParser()
    parser.add_argument("--filelist", type=str)
    parser.add_argument("--zippath", type=str)
    parser.add_argument("--index_part", type=int, default=0)
    parser.add_argument('--num_parts', type=int, default=1)
    parser.add_argument('--redo', action='store_true', help='', default=False)
    args = parser.parse_args()
    
    args.root_path = args.filelist 
    if os.path.isfile(args.root_path):
        with open(args.root_path,'r') as f:
            all_file_list = [t.strip() for t in f.readlines()]
    else:
        all_file_list = [args.root_path]
    #all_file_list = [DIR.replace('unprocessed_tex','unprocessed_xml') for DIR in all_file_list if os.path.getsize(DIR) > 0]
    
    index_part= args.index_part
    num_parts = args.num_parts 
    totally_paper_num = len(all_file_list)
    logging.info(totally_paper_num)
    if totally_paper_num > 1:
        divided_nums = np.linspace(0, totally_paper_num , num_parts+1)
        divided_nums = [int(s) for s in divided_nums]
        start_index = divided_nums[index_part]
        end_index   = divided_nums[index_part + 1]
    else:
        start_index = 0
        end_index   = 1
        verbose = True

    all_file_list = all_file_list[start_index: end_index]
    batch_extract(all_file_list, args.zippath, args.index_part)