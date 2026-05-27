import os

os.environ['EVAL_DIALECT'] = os.getenv('EVAL_DIALECT', 'postgres')
from eval_execution_runner import main

if __name__ == '__main__':
    main()
