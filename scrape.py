import time
import cloudscraper
from bs4 import BeautifulSoup
import json
import random
import boto3
import time
import datetime

#TO RUN LOCAL: Uncomment call to main(a,b) at bottom
#TO RUN LAMBDA: Comment call to main(a,b)
#				Package into zip
#				Upload into lambda

#v0.9
#better class instantiation, now automatically assigns json variables to class. Question: Do we bother with JSON if we can blatantly just run the URLs copied and pasted? Yeah I guess so.
#v0.92 add to carobjectclass the ability to have a dictionary which records the identifiers from json
#v0.93 change the query type to be modifyable for bottom 10 and top 10
#v0.93.3 break up the big site read into separate scraping and parsing activities
#v0.93.4 write to AWS
#v0.93.5 many error handling improvements; ad result removal
#v0.93.7 fixed the processing of prices and mileage to remove commas which were terrible - str.replace('£', '')
#        fixed to run in lambda by making sure main function can handle the two lambda inputs (event, something else)
#        now needs compressing into package.zip which also includes all the includes stuff packaged at the same directory level.
# TODO add a database in the middle because it's getting silly to open files and do comma separation.

#Need to import to here from the other program. Or maybe modulify the other program?
#Perhaps a moduled method to get the cars
#Should really change this to move the 'output', 'buildurl' and other methods into the class, as class methods. Makes much more sense. Will allow easy updating of each object too.

class carresult :
	def __init__(self) :
		self.price = '' 
		self.mileage = ''
		self.year = ''

class Carobjectclass :
	#needs updating to __init__ else variables get shared
	def __init__(self) :
		self.make = ''
		self.model = ''
		self.carsearchurl = ''
		self.caryearfrom = ''
		#self.cheapestcarsfound = []
		# also will have self.identifiersfromjson

	# htt://www.autotrader.co.uk/car-search?sort=relevance&postcode=gu12aj&radius=1500&make=MCLAREN&model=570S&aggregatedTrim=T%20V8&include-delivery-option=on
	def buildurl(self): # Build a new URL from stored attributes
		self.carsearchurl = '' # Start with
		for key, value in self.identifiersfromjson.items() :
			self.carsearchurl = self.carsearchurl + '&' + key + '=' + value
		print('URL built ', self.carsearchurl)

	def addjsonidentifierstodict(self,carfromjson) :
		self.identifiersfromjson = {}
		for key in carfromjson :
			self.identifiersfromjson[key] =  carfromjson[key]
		self.friendlyname = carfromjson['friendlyname']
		self.identifiersfromjson['postcode'] = 'AL11QF'
		self.identifiersfromjson['radius'] = '1500'
		self.identifiersfromjson['include-delivery-option'] = 'on'

# end car object class


def	getqueriesfromjson() : # read json, output list of cars
	# Choose your desired file source here:
	source = 's3'
	#source = 'local'
	if source == 's3' :
		s3 = boto3.resource('s3')
		s3fileobject = s3.Object('outrundrop-output', 'sourcecars.json')
		try :
			sourcecarsstring = s3fileobject.get()['Body'].read().decode('utf-8')
			listofcarstoqueryfromjson = json.loads(sourcecarsstring)['cars']
		except s3.meta.client.exceptions.NoSuchKey as error :
			print('No Source File Found , selected source was ', source)
		return listofcarstoqueryfromjson
	# Local file
	if source == 'local' :
		with open('cars2.json') as f:
			listofcarstoqueryfromjson = json.load(f)['cars'] # list
			return listofcarstoqueryfromjson

def main(event, context) : # read from disk, create objects, add URLs, parse URLs, add carresult objects for each result
	listofcarstoqueryfromjson = getqueriesfromjson()
	listofcarobjects = createcarobjects(listofcarstoqueryfromjson) #Create object for each car, store in a list
	for carobject in listofcarobjects :
		carobject.buildurl()
	listofcarobjects = readSite(listofcarobjects, 'price-asc') # read site with the URL stored in the object
	#listofcarobjects = readSite(listofcarobjects, 'price-desc') # read site with the URL stored in the object
	output(listofcarobjects, 'price-asc')
	outputlowestprice(listofcarobjects, 'price-asc')
	#output(listofcarobjects, 'price-desc')
	notify(listofcarobjects)
	return {
        "statusCode": 200,
        "body": json.dumps('Hello this was the scraper reporting back from the end of the Lambda!')
    }

# scrape, get soup, add soup to carobject, break down tags
def readSite(listofcarobjects, sort) :
	urlstart = 'https://www.autotrader.co.uk/car-search?sort=' + sort
	i = 0
	for carobject in listofcarobjects :
		while True :
			try :
				scraper = cloudscraper.create_scraper(browser={
        		'browser': 'chrome',
        		'platform': 'windows',
        		'mobile': False
    			})  # returns a CloudScraper instance
				print("querying " + urlstart + carobject.carsearchurl)
				html = scraper.get(urlstart + carobject.carsearchurl).text
				soup = BeautifulSoup(html, 'html.parser') # note could use , multi_valued_attributes=None to handle spaces in 'class' strings
				s3 = boto3.resource('s3')
				s3fileobject = s3.Object('outrundrop-output', 'rawhtml/' + carobject.identifiersfromjson['friendlyname'] + '-raw-' +  str(time.time()) + '.html')
				s3fileobject.put(Body=bytes(html, 'utf-8'))
				searchpageresultstag = soup.find('div',class_="search-page__results") # Boy this seems ugly - do it again if it failed
				listofsearchpageresults = searchpageresultstag.find_all('li', class_="search-page__result")
				time.sleep(random.randrange(3,7)) # sleep a bit to prevent being blocked for overuse
				break
			except AttributeError :
				print('found no tags - retrying yo')
		setattr(carobject, 'soup'+sort, soup)
		#Optional: Add another URL lookup here to look less like a bot ?
		i = i+1
		#time.sleep(random.randrange(3,7)) # sleep a bit to prevent being blocked for overuse
		carobject = processtags(carobject, soup, sort)
		print("Read Site and done tags for " + str(i) + " out of " + str(len(listofcarobjects)) + " desired cars to read.")
	return listofcarobjects

def processtags(carobject, soup, sort) :
	searchpageresultstag = soup.find('div',class_="search-page__results") # Tag
	# ITERATE ALL RESULTS FOUND and add car result objects to the car object under the relevant list depending on search sort type
	#Need below to only find results without the advert attribute
	listofsearchpageresults = searchpageresultstag.find_all('li', class_="search-page__result") # put all result vehicles in a list
	#create the empty list of objects
	setattr(carobject, sort, [] )
	for i in range(0,len(listofsearchpageresults) - 1):
		#skip results that are ads
		if 'data-is-featured-listing=\"true\"' in str(listofsearchpageresults[i])  :
			print('do nothing - this was a featured ad')
		else :
			thiscarresultobject = carresult() # create new car result object which will later be added to a list within the main car object
			thiscarresultobject.price = listofsearchpageresults[i].find('div', class_="product-card-pricing__price").span.text.replace('£','').replace(',','')
			parseresultdetailssection(listofsearchpageresults[i],thiscarresultobject)
			#how to set append an object 
			getattr(carobject, sort).append(thiscarresultobject)
	print ('processed ', str(len(listofsearchpageresults) - 1), ' tags')
	return carobject


def parseresultdetailssection(thissearchpageresult, thiscarresultobject) :
	keyspecsection = thissearchpageresult.find('ul',class_="listing-key-specs")
	specslist = keyspecsection.find_all('li')
	# Sometimes results cards are more per page and only show 2 listing specs ; check for this 
	thiscarresultobject.year = specslist[0].text
	if len(specslist) > 3 :
		thiscarresultobject.mileage = specslist[2].text.replace(',','').replace(' miles','')
	else :
		thiscarresultobject.mileage = ''


def createcarobjects(listofcarstoqueryfromjson) :
	listofcarobjects = [] 
	for carfromjson in listofcarstoqueryfromjson :
		carobject = Carobjectclass()
		carobject.addjsonidentifierstodict(carfromjson)
		listofcarobjects.append(carobject) # Add new object with its json identifiers recorded
	return listofcarobjects



def output(listofcarobjects, sort) :
	for carobject in listofcarobjects :
		# to screen
		print ("Results for " + carobject.identifiersfromjson['friendlyname'])
		outputstring = carobject.identifiersfromjson['friendlyname'] + '\n'
		for carfound in getattr(carobject, sort) :
			outputstring = outputstring + carfound.price +  ',' + carfound.mileage +  ',' + carfound.year + '\n'
		print(outputstring)
		# to s3
		print("Writin to S3 woo")
		s3 = boto3.resource('s3')
		
		#s3fileobject = s3.Object('outrundrop-output', 'bototest-' + str(time.time()) + '.json')
		s3fileobject = s3.Object('outrundrop-output', 'found/' + carobject.identifiersfromjson['friendlyname'] + '.csv')
		s3fileobject.put(Body=bytes(outputstring, 'utf-8'))


def outputlowestprice(listofcarobjects, sort) :
	for carobject in listofcarobjects :
		# to screen
		print ("Lowest Results for " + carobject.identifiersfromjson['friendlyname'])
		outputstring = ''
		#select very first result, i.e. the cheapest
		carfound = getattr(carobject, sort)[0]
		outputstring = outputstring + carfound.price +  ',' + carfound.mileage +  ',' + carfound.year + ',' + str(datetime.datetime.now()) + '\n'
		print(outputstring)
		# to s3
		print("Writin lowest price to S3 woo")
		s3 = boto3.resource('s3')
		#s3fileobject = s3.Object('outrundrop-output', 'bototest-' + str(time.time()) + '.json')
		s3fileobject = s3.Object('outrundrop-output', 'lowest/' + carobject.identifiersfromjson['friendlyname'] + '-lowest-' + '.csv')
		#need to catch and ignore errors here:
		#Read current entries, append. Use empty string if didn't already exist.
		try :
			currententries = s3fileobject.get()['Body'].read().decode('utf-8')
		
		except s3.meta.client.exceptions.NoSuchKey as error :
			currententries = ''
		outputstring = currententries + outputstring
		s3fileobject.put(Body=bytes(outputstring, 'utf-8'))

def notify(listofcarobjects) :
	snsclient = boto3.client('sns')
	message = 'ReadAT processed ' + str(len(listofcarobjects)) + ' vehicles.\n'
	for carobject in listofcarobjects :
		carfound = getattr(carobject, 'price-asc')[0]
		message = message + carobject.friendlyname + ' ' + carfound.price + '\n'
	response = snsclient.publish(
		PhoneNumber='+447980242438',
		Message=message
	)

main('a','b')
