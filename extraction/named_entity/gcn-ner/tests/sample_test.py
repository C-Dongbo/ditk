import unittest
import pandas as pd
import ner 
import main
import ner_gcn

class TestNERMethods(unittest.TestCase):

    def setUp(self):
        self.ner = ner_gcn.GcnNer()
        self.input_file = './data/input.txt'    # Input file is in /gcn-ner/data/
        self.output_file = main.main(self.input_file)

    def row_col_count(self, file_name):
        df = pd.read_csv(file_name,delimiter = ' ')
        return df.shape

    def test_outputformat(self):
        input_row_count = self.row_col_count(self.input_file)[0]
        input_col_count = self.row_col_count(self.input_file)[1]
        output_row_count = self.row_col_count(self.output_file)[0]
        output_col_count = self.row_col_count(self.output_file)[1]

        self.assertEqual(input_row_count, output_row_count)
        self.assertEqual(output_col_count, 3)

if __name__ == '__main__':
    unittest.main()
