# Usage

```
python python_script/html_to_json.py --root datasets/ar5iv/no_problem.html.filelist --savepath datasets/ar5iv/no_problem_json/ 
```

- the .filelist should be the abspath for each html file such as 

  ```
  datasets/ar5iv/no-problem/0003/cond-mat0003325.html
  datasets/ar5iv/no-problem/0003/hep-ph0003287.html
  datasets/ar5iv/no-problem/0003/gr-qc0003030.html
  datasets/ar5iv/no-problem/0003/astro-ph0003274.html
  datasets/ar5iv/no-problem/0003/cond-mat0003474.html
  datasets/ar5iv/no-problem/0003/astro-ph0003320.html
  datasets/ar5iv/no-problem/0003/astro-ph0003298.html
  datasets/ar5iv/no-problem/0003/cond-mat0003427.html
  datasets/ar5iv/no-problem/0003/physics0003094.html
  datasets/ar5iv/no-problem/0003/math0003213.html
  ```

- it will save the `.json` format file follow the same direction under `savepath` such as 

  ```
  datasets/ar5iv/no_problem_json/0003/cond-mat0003325/ar5iv/cond-mat0003325.json
  datasets/ar5iv/no_problem_json/0003/hep-ph0003287/ar5iv/hep-ph0003287.json
  datasets/ar5iv/no_problem_json/0003/gr-qc0003030/ar5iv/gr-qc0003030.json
  datasets/ar5iv/no_problem_json/0003/astro-ph0003274/ar5iv/astro-ph0003274.json
  datasets/ar5iv/no_problem_json/0003/cond-mat0003474/ar5iv/cond-mat0003474.json
  datasets/ar5iv/no_problem_json/0003/astro-ph0003320/ar5iv/astro-ph0003320.json
  datasets/ar5iv/no_problem_json/0003/astro-ph0003298/ar5iv/astro-ph0003298.json
  datasets/ar5iv/no_problem_json/0003/cond-mat0003427/ar5iv/cond-mat0003427.json
  datasets/ar5iv/no_problem_json/0003/physics0003094/ar5iv/physics0003094.json
  datasets/ar5iv/no_problem_json/0003/math0003213/ar5iv/math0003213.json
  ```

- Active multiprocessing by adding `--batch_num [thread_num]` such as 

  `python python_script/html_to_json.py --root datasets/ar5iv/no_problem.html.filelist --savepath datasets/ar5iv/no_problem_json/ --batch_num 32` 

- Avoid analysis and put back note by adding `--passNote`