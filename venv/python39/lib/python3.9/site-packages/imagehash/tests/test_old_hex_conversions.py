import unittest
import numpy as np
import imagehash


# Each row is a test case where the first value is a hexadecimal
# sequence and the second value is the expected bool array for it.
old_hexadecimal_to_bool_array = [
	['ffeb89818193ffff', np.array([ [True, True,  True,  True,  True,  True,  True,  True],
									[True, True,  False, True,  False, True,  True,  True],
									[True, False, False, True,  False, False, False, True],
									[True, False, False, False, False, False, False, True],
									[True, False, False, False, False, False, False, True],
									[True, True,  False, False, True,  False, False, True],
									[True, True,  True,  True,  True,  True,  True,  True],
									[True, True,  True,  True,  True,  True,  True,  True]]) ],
]

class TestOldHexConversions(unittest.TestCase):

	def setUp(self):
		self.from_hex = imagehash.old_hex_to_hash

	def test_hex_to_hash_output(self):
		for case in old_hexadecimal_to_bool_array:
			self.assertTrue(np.array_equal(case[1], self.from_hex(case[0]).hash))


if __name__ == '__main__':
	unittest.main()
