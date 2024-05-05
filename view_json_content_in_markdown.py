import json
import sys

JsonFilePath = sys.argv[1] #/nvme/zhangtianning/datasets/whole_arxiv_data/whole_arxiv_old_quant_ph/unprocessed_json/0711.3850/0711.3850.retrieved.json

with open(JsonFilePath, 'r') as f:
    content = json.load(f)
if content['abstract']:
    print("#","Abstract")
    print(content['abstract'])
if content['sections']:
    for section_num, section in enumerate(content['sections']):
        if 'section_title' in section:
            print("#", section['section_title'])
        elif 'tag' in section:
            print("#", 'Section', section['tag'])
        elif 'section_num' in section:
            print("#", 'Section', section['section_num'])
        else:
            print('#', 'Section', section_num)
        for paragraph in section['section_content']:
            if isinstance(paragraph, str):
                paragraph = [paragraph]
            for sentence in paragraph:
                print(sentence.replace("$$","$"))
            print('\n')

