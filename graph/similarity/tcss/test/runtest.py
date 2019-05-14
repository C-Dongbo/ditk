import unittest
from .. import main

class TestTSCC(unittest.TestCase):
	def setUp(self):
		self.input_file = "data/positives.sgd.c"
		self.output_file = main.main(self.input_file)
	def get_file(self, file_name):
		f = open(file_name)
		s = ''
		for i in f: s+=i
		return i
	def test_output(self):
		standard = "data/example_output.txt"
		generated_output = self.get_file(self.output_file)
		standard_output  = self.get_file(standard)
		self.assertEqual(generated_output, standard_output)
	
if __name__ == '__main__':
    unittest.main()
	