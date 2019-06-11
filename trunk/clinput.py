def user_input ():
	try:
		row_number = int(raw_input("How many buildings in a row should be generated?\n"))
		return row_number
	except ValueError:
		print "Input was not recognised as integer/n"
		print "Number of building rows will default to 40"
		return 40
