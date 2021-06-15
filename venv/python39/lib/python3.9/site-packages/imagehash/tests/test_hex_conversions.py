import unittest
import numpy as np
import imagehash


# Each row is a test case where the first value is a bit sequence and
# the second value is the expected hexadecimal representation for it.
binary_to_hexadecimal_values = [
	['1', '1'],
	['11', '3'],
	['111', '7'],
	['1111', 'f'],
	['10000', '10'],
	['110000', '30'],
	['1110000', '70'],
	['11110000', 'f0'],
	['00001', '01'],
	['000011', '03'],
	['0000111', '07'],
	['00001111', '0f'],
	['10000001', '81'],
	['00000000000000001', '00001'],
	['000000000000000011', '00003'],
	['0000000000000000111', '00007'],
	['00000000000000001111', '0000f'],
	['11110000111100001111', 'f0f0f'],
	['00001111000011110000', '0f0f0'],
	['11110000000100100011010001010110011110001001101010111100110111101111', 'f0123456789abcdef'],
	['1001111000111100110000011111000011110000110000111110011111000000', '9e3cc1f0f0c3e7c0'],
	['1000111100001111000011110000111100001111000010110000101101111010', '8f0f0f0f0f0b0b7a'],
]

# Each row is a test case where the first value is a hexadecimal sequence
# and the second value is the expected binary representation for it.
hexadecimal_to_binary_values = [
	['1', '0001'],
	['2', '0010'],
	['3', '0011'],
	['a', '1010'],
	['f', '1111'],
	['101', '100000001'],
	['1b1', '110110001'],
	['0b1', '010110001'],
	['f0f0', '1111000011110000'],
	['0f0f', '0000111100001111'],
	['000c', '0000000000001100'],
	['100000d', '1000000000000000000001101'],
	['000000d', '0000000000000000000001101'],
	['000000001', '000000000000000000000000000000000001'],
	['800000001', '100000000000000000000000000000000001'],
	['0000000000001', '0000000000000000000000000000000000000000000000001'],
	['1000000000001', '1000000000000000000000000000000000000000000000001'],
	['0000000000000001', '0000000000000000000000000000000000000000000000000000000000000001'],
	['8000000000000001', '1000000000000000000000000000000000000000000000000000000000000001'],
]

# Each row is a test case where the first value is a hexadecimal
# sequence and the second value is the expected bool array for it.
hexadecimal_to_bool_array = [
	['9e3cc1f0f0c3e7c0', np.array([ [True,  False, False, True,  True,  True,  True,  False],
									[False, False, True,  True,  True,  True,  False, False],
									[True,  True,  False, False, False, False, False, True],
									[True,  True,  True,  True,  False, False, False, False],
									[True,  True,  True,  True,  False, False, False, False],
									[True,  True,  False, False, False, False, True,  True],
									[True,  True,  True,  False, False, True,  True,  True],
									[True,  True,  False, False, False, False, False, False]]) ],
]

class TestHexConversions(unittest.TestCase):

	def setUp(self):
		self.to_hex = imagehash._binary_array_to_hex
		self.from_hex = imagehash.hex_to_hash

	def test_binary_array_to_hex_input(self):
		for case in hexadecimal_to_bool_array:
			self.assertEqual(case[0], self.to_hex(case[1]))

	def test_hex_to_hash_output(self):
		for case in hexadecimal_to_bool_array:
			self.assertTrue(np.array_equal(case[1], self.from_hex(case[0]).hash))

	def test_conversion_to_hex(self):
		for case in binary_to_hexadecimal_values:
			expected = case[1]
			bit_array = np.array([int(d) for d in case[0]])
			result = self.to_hex(bit_array)
			self.assertEqual(expected, result)

	def test_conversion_from_hex(self):
		for case in hexadecimal_to_binary_values:
			expected = case[1]
			result = ''.join(str(b) for b in 1 * self.from_hex(case[0]).hash.flatten())
			self.assertEqual(expected, result)


if __name__ == '__main__':
	unittest.main()
