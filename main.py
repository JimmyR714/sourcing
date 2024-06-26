from openai import OpenAI
import json
import requests
import pandas as pd
from operator import itemgetter
import os
from dotenv import load_dotenv
from embeddings_utils import *

#loads API key for crunchbase, TODO when implementing at Vela, put your api key in a .env file
load_dotenv()
CB_API_KEY = os.getenv("CB_API_KEY")

# Constants 
EXPENSIVE_MODE = True #this will cost more to run. uses higher quality LLMs and does more calls to them too
# TODO have funding be a parameter inputted by LLM to crunchbase search
MAX_FUNDING = 1000000000 #Can be adjusted manually here 
TESTING = False #this adds some useful debugging features and additional outputs, specifically used for checking accuracy of each stage right now

client = OpenAI()

# Function to get the embedding for some text. Primarily used for comparing with query
def get_embedding(text, model = "text-embedding-3-small"):
    text = text.replace("\n", " ") #tidy text
    return client.embeddings.create(input = [text], model=model).data[0].embedding

# Function to search crunchbase for results related to certain categories
# The categories are permalinks on Crunchbase
# n represents the number of items to find, n=-1 represents the maximum (all related companies)
# Returns a dataframe containing the companies found

# TODO add more parameters to this function to make the search more customisable, although a warning for this is that
# TODO it is smart to use permalinks or uuids when searching for things like locations, mirror my method for categories if necessary
def searchCrunchbaseCompanies(categories, n=-1):
    # Function to count the number of Crunchbase companies that appear in a given category search
    def countCrunchbaseCompanies(query):
        url = "https://api.crunchbase.com/api/v4/searches/organizations?user_key=" + CB_API_KEY
        headers = {"accept": "application/json"}
        r = requests.post(url=url, headers=headers, json = query | {"field_ids":["identifier"]})
        result = json.loads(r.text)
        total_companies = result["count"]
        return int(total_companies)

    # Function to extract companies from Crunchbase
    def extractCompanies(m, raw):
        r = requests.post(url=url, headers=headers, json=queryJSON | {"limit":m})
        result = json.loads(r.text) #JSON containing all companies from this query

        #clean the data
        normalized_raw = pd.json_normalize(result["entities"])
        return pd.concat([raw, normalized_raw], ignore_index = True)

    # The search query
    query = {
        "query": [
            {
                "type": "predicate",
                "field_id": "categories",
                "operator_id": "includes",
                "values": categories #only look for companies including these categories
            },
            {
                "type": "predicate",
                "field_id": "facet_ids",
                "operator_id": "includes",
                "values": ["company"] #finding only companies
            },
            {
                "type": "predicate",
                "field_id": "funding_total",
                "operator_id": "lt",
                "values": [MAX_FUNDING] #funding less than MAX_FUNDING
            },
            {
                "type": "predicate",
                "field_id": "operating_status",
                "operator_id": "eq",
                "values": ["active"] #active companies
            },
            {   #TODO allow founding date to be adjusted by LLM
                "type": "predicate",
                "field_id": "founded_on",
                "operator_id": "gte",
                "values": [2021] #founding date after 2021
            } 
        ]
    }

    #Find out how many companies we should find
    if n == -1:
        limit = countCrunchbaseCompanies(query)
    else:
        limit = n
    
    # The full JSON that we search with
    queryJSON = {
        "field_ids": [
            "identifier",
            "short_description",
            "categories",
            "num_employees_enum",
            "revenue_range",
            "website_url",
            "funding_total",
            "funding_stage",
            "founder_identifiers",
            "investor_identifiers",
            "num_investors",
            "rank_delta_d7",
            "rank_delta_d30",
            "rank_delta_d90",
            "rank_org",
            "location_identifiers",
            "founded_on",
            "operating_status"
        ],
        "order": [
            {
                "field_id": "rank_org",
                "sort": "asc"
            }
        ]
    } | query

    url = "https://api.crunchbase.com/api/v4/searches/organizations?user_key="+CB_API_KEY
    headers = {"accept": "application/json"}

    raw = pd.DataFrame()
    #loop until we get limit companies
    data_acquired = 0
    while data_acquired < limit:
        if data_acquired != 0: #if we already searched for some companies
            queryJSON["after_id"] = raw["uuid"][len(raw["uuid"])-1]
        else:
            #pop after_id just in case it exists
            if "after_id" in queryJSON:
                queryJSON = queryJSON.pop("after_id")
        #searches up to a maximum of 1000 companies
        raw = extractCompanies(min(1000, limit - data_acquired), raw)
        data_acquired = len(raw["uuid"])

    revenue_range = {
    "r_00000000": "Less than $1M",
    "r_00001000": "$1M to $10M",
    "r_00010000": "$10M to $50M",
    "r_00050000": "$50M to $100M",
    "r_00100000": "$100M to $500M",
    "r_00500000": "$500M to $1B",
    "r_01000000": "$1B to $10B",
    "r_10000000": "$10B+"}

    employee_range = {
    "c_00001_00010": "1-10",
    "c_00011_00050": "11-50",
    "c_00051_00100": "51-100",
    "c_00101_00250": "101-250",
    "c_00251_00500": "251-500",
    "c_00501_01000": "501-1000",
    "c_01001_05000": "1001-5000",
    "c_05001_10000": "5001-10000",
    "c_10001_max": "10001+"}

    #process data we have acquired
    master = pd.DataFrame()
    master["uuid"] = raw["uuid"]
    master["founded_on"] = raw["properties.founded_on.value"]
    master["company"] = raw["properties.identifier.value"]
    master["description"] = raw["properties.short_description"]
    master["categories"] = raw["properties.categories"].apply(lambda x: list(map(itemgetter('value'), x)if isinstance(x, list) else ["Not found"])).apply(lambda x : ",".join(map(str, x)))
    master["num_of_employees"] = raw["properties.num_employees_enum"].map(employee_range)
    master["revenue"] = raw["properties.revenue_range"].map(revenue_range)
    master["website"] = raw["properties.website_url"]
    master["location"] = raw["properties.location_identifiers"].apply(lambda x: list(map(itemgetter('value'), x)if isinstance(x, list) else ["Not found"])).apply(lambda x : ",".join(map(str, x)))
    master["funding"] = raw["properties.funding_total.value_usd"]
    master["funding_stage"] = raw["properties.funding_stage"]
    master["founder_names"] = raw["properties.founder_identifiers"].apply(lambda x: list(map(itemgetter("value"), x)if isinstance(x, list) else ["Not found"])).apply(lambda x : ",".join(map(str, x)))
    master["founder_uuids"] = raw["properties.founder_identifiers"].apply(lambda x: list(map(itemgetter('uuid'), x)if isinstance(x, list) else ["Not found"])).apply(lambda x : ",".join(map(str, x)))
    master["investors"] = raw["properties.investor_identifiers"].apply(lambda x: list(map(itemgetter('value'), x)if isinstance(x, list) else ["Not found"])).apply(lambda x : ",".join(map(str, x)))
    master["num_of_investors"] = raw["properties.num_investors"]
    master["rank_change_week"] = raw["properties.rank_delta_d7"]
    master["rank_change_month"] = raw["properties.rank_delta_d30"]
    master["rank_change_quarter"] = raw["properties.rank_delta_d90"]
    master["rank"] = raw["properties.rank_org"]
    master["status"] = raw["properties.operating_status"]
    master=master.fillna("NA")

    #print(master.to_string())
    return master

# Function that finds the founder backgrounds from a list of founder UUIDs
# TODO Currently uses crunchbase which has almost no information on founders, but can be easily adjusted to use another API with more info on people
def founderBackgrounds(founderUUIDList):
    founderUUIDs = founderUUIDList.split(",")
    founders = ""
    for UUID in founderUUIDs:
        founders += outputFounder(searchCrunchbaseFounder(UUID)) + ". "
    return founders

# Function that searches crunchbase for founders/investors given their uuid
# Much more information can be acquired if necessary
# returns a json containing the information about the person
def searchCrunchbaseFounder(founderUUID):
    #attempt to retrieve the data
    def attemptRetrieval(into, outOf):
        try:
            founder.update({into: raw[outOf].values[0]})
        except:
            founder.update({into: "Not Found"})

    # a lot more information could be added to each of these functions, but we need to be careful not to do too much or else
    # evaluating the quality will get expensive and detract from what we want LLM to look for
    def getDegree(d):
        return "Type: " + d["type_name"] + "; School: " + d["school_identifier.value"] + "; Subject: " + d["subject"] + "Completed on: " + d["completed_on"]

    def getJob(j):
        return "Title: " + j["title"] + "; Employer: " + j["organization_identifier"] + "; Started: " + j["started_on.value"] + "; Finished: " + j["ended_on.value"]
        
    def getCompany(c):
        return "Name: " + c["identifier.value"] + "; Description: " + c["short_description"] + "; Funding: " + c["funding"] + "; Status: " + c["status"]

    url = f"https://api.crunchbase.com/api/v4/entities/people/{founderUUID}?user_key="+CB_API_KEY
    r = requests.get(url=url)
    result = json.loads(r.text) #JSON containing all information about the founder

    #clean the data
    raw = pd.json_normalize(result)
    founder = {}
    attemptRetrieval("name", "properties.identifier.value")
    attemptRetrieval("gender", "properties.gender")
    attemptRetrieval("born_on", "properties.born_on")
    attemptRetrieval("location", "properties.location_identifiers")
    try:
        founder.update({"degrees":raw["cards.degrees"].apply(lambda x: list(map(getDegree, x) if isinstance(x, list) else ["Not found"])).apply(lambda x : ",".join(map(str, x)))})
    except:
        founder.update({"degrees": "Not Found"})
    try:
        founder.update({"jobs": raw["cards.jobs"].apply(lambda x: list(map(getJob, x) if isinstance(x, list) else ["Not found"])).apply(lambda x : ",".join(map(str, x)))})
    except:
        founder.update({"jobs": "Not Found"})
    try:
        founder.update({"companies": raw["cards.founded_organizations"].apply(lambda x: list(map(getCompany, x) if isinstance(x, list) else ["Not found"])).apply(lambda x : ",".join(map(str, x)))})
    except:
        founder.update({"companies": "Not Found"})

    return founder

# Function that takes a json for a founder and formats it into a string
def outputFounder(founder):
    #we use this function to avoid a messy output full of "Not Found"
    def attemptAdd(title, type):
        content = founder[type]
        if content != "Not Found":
            output += title + ": " + content + "; "
    
    attemptAdd("Name", "name")
    attemptAdd("Gender", "gender")
    attemptAdd("Born on", "born_on")
    attemptAdd("Located in", "location")
    attemptAdd("Degrees", "degrees")
    attemptAdd("Previous Jobs", "jobs")
    attemptAdd("Previous Companies", "companies")

# Function that takes a dataframe of companies, a query, 
# and reduces the dataframe to the n most relevant companies
# Returns the refined dataframe
def refine(df, query, n=100):
    #process table into information that LLM can use to create embedding
    #TODO have the information added here be customisable by the LLM
    df["pre-embedding"] = (
        "Name: " + df["company"].str.strip() +
        "; Summary: " + df["description"].str.strip() +
        "; Industries: " + df["categories"].str.strip() +
        "; Location: " + df["location"].str.strip() #more info could be added, but may distract LLM
        )
    
    if EXPENSIVE_MODE:
        model = "text-embedding-3-large"
    else:
        model = "text-embedding-3-small"
    df["embedding"] = df["pre-embedding"].apply(lambda x: get_embedding(x, model=model))

    #get the embedding for the query
    query_embedding = get_embedding(query,model=model)

    #find relevance of companies
    df["embedding_distance"] = df["embedding"].apply(lambda x: abs(distance_from_embedding(query_embedding, x, distance_metric="cosine")))
    #choose the n most relevant companies
    refined = df.nsmallest(n, "embedding_distance")

    if TESTING:
        refined.to_csv(f"sourcing/refinement/embeddings{query[0]}.csv",  
            columns = ["company", "description", "founded_on", "categories", "num_of_employees", "revenue", "website", "location", "funding", 
                "funding_stage", "founder_names", "founder_uuids", "investors", "num_of_investors", "rank_change_week", "rank_change_month", 
                "rank_change_quarter", "rank", "status", "embedding_distance"],
            sep="\t", encoding="utf-8") #only used for testing, also storage of top 100 companies

    return refined.reset_index()

# Function to load the crunchbase categories from a file
def loadCategories():
    with open("sourcing\permalinks.txt") as file:
        return [line.rstrip() for line in file]

# Function that takes a query and returns crunchbase categories that most relate to that query
# Currently requires category list; may be difficult to adapt to work without the category list
def chooseCategory(query):
    categoryList = loadCategories()
    messages = [
        {
            "role": "system", 
            "content": 
                """
                You are a helpful assistant that takes an input query which is a description of a company. 
                Your job is to turn this query into a series of categories that most relate to the company description.
                You can return up to 3 different categories, but your main goal is to be precise, so if you can't find 3 suitable categories,
                you may return only 1. You must return at least 1 category. You have a list of categories to choose from, 
                the categories that you return must be selected from this list. The categories are separated by commas.
                The list is: 
                """ + ", ".join(map(str,categoryList))
        },
        {
            "role": "user",
            "content": 
                """
                Q: Find me the top 10 IT companies that do consulting.
                A: 
                IT stands for information technology, so I should include the category "information-technology" from the list. 
                The query mentions consulting, so I should include "consulting". There are no other relevant categories, so
                the answer is ["information-technology", "consulting"]
                Q: Find me the top 10 biotech companies that are researching AI.
                A: 
                Biotech is short for biotechnology, so I must include the category "biotechnology" from the list. 
                We need companies researching AI, AI is short for artificial intelligence, so I should include the
                category "artificial-intelligence" from the list. There is no category for research, so I have all of the
                relevant categories, so the answer is ["biotechnology", "artificial-intelligence"]
                Q: 
                """+query
        }
    ]

    #allow LLM to choose categories
    response = client.chat.completions.create(model="gpt-4-turbo-preview", messages=messages)
    return response.choices[0].message.content

#TODO implement the following searching tools 
# Function to search github for results related to a query
# q is a carefully formatted query
# Returns a list of length n containing companies that match the query
def searchGithub(query, n=100):
    pass

# Function to search product hunt for results related to a query
# q is a carefully formatted query
# Returns a list of length n containing companies that match the query
def searchProductHunt(query, n=100):
    pass

# Function to search hackernews for results related to a query
# q is a carefully formatted query
# Returns a list of length n containing companies that match the query
def searchHackernews(query, n=100):
    pass

# Function that ranks the top n companies out of a larger set
# Input is the dataframe containing all of the information about each company 
# This input data includes founder information
# Outputs the top n companies as a list of indices
def rank(companies, query, n=10):
    #TODO ToT implementation can be much cleaner and more advanced here, this is only very basic to ensure evaluation is decent
    company_info = companies.apply((lambda r: f"""
        UUID: {r["uuid"]}; Name: {r["company"]}; Description: {r["description"]}; Categories: {r["categories"]}; Employees: {r["num_of_employees"]}; Revenue: {r["revenue"]};
        Location: {r["location"]}; Funding: {str(r["funding"])}; Funding Stage: {r["funding_stage"]}; 
        Number of Investors: {r["num_of_investors"]}; Top Investors: {str(r["investors"])}; 
        Weekly Rank Change: {str(r["rank_change_week"])}; Monthly Rank Change: {str(r["rank_change_month"])}; Quarterly Rank Change: {str(r["rank_change_quarter"])};
        Rank: {str(r["rank"])}; Founders: {r["founder_backgrounds"]}
        """), axis=1).to_string()
    
    def thought():
        messages = [
            {
                "role": "system", 
                "content": 
                    f"""
                    You are a helpful assistant that takes as input a set of companies. Your job is to 
                    choose the {str(n)} most relevant companies according to the following criteria:
                    1) The company must be relevant to the query
                    2) The company must be big enough, e.g. a decent number of employees or a decent amount of funding, 
                    or a few investors. We don't want very small companies
                    3) Companies that have founders that are based in the US are better than those that don't
                    4) Companies that have founders that have degrees from top-tier universities 
                    e.g. Oxford, Cambridge, Harvard, Stanford, MIT, etc are better that those that don't
                    5) Companies that have founders that have previously been employed by top-tier companies 
                    e.g. Google, Amazon, Apple, Meta etc are better than those that don't
                    6) Companies that have founders that have had previous entrepeneurial success
                    e.g. founding a company with a high valuation, founding a company that has been acquired, etc
                    are better than those that don't
                    7) Companies that have a higher improvement over the last quarter, month and week are better
                    8) Companies that have top-tier investors are better than those that don't
                    You should evaulate the companies according to all criteria, with slightly more weight
                    given to the higher criteria e.g. 1,2 than the lower ones.
                    You should output the top {str(n)} companies by descending evaluation score that you have chosen. 
                    You should output this as a list of their indices within the table. 
                    You should also output your reasons for choosing each company in this top {str(n)} in less than 10 words.
                    Make sure this evaluation explains why you chose it and how it relates to the criteria. 
                    Ensure that each evaluation is very relevant to the company chosen. This means you cannot make up any facts about the company
                    e.g. If you know the name of the founder but no information about their background, you cannot include their education or past jobs as part of the evaluation,
                    as you do not know them. The evaluation must consist of real facts that you have been told about the company.
                    Make it very clear which evaluation belongs to which company by including the name of each company chosen within its evaluation.
                    Even if many of the facts are missing, give a rough evaluation anyway, ensure you return the top 10 companies.
                    You MUST return the top 10 companies, with their evaluations, if there isn't much information, do this based on
                    the company description. The evaluations only need to be a short sentence.
                    """
            },
            { #these fake companies were generated by ChatGPT, so information is random. this is ideal as it gives a good variety of companies
                "role": "user", 
                "content": """
                    Q: The query is: companies that specialise in AI image recognition software
                    The companies are: 
                    UUID = 7283924-cdcb-4111-bc94-f22cd91r72e8
                    Name: SmarTech
                    Description: Technology company specialising in development of AI games
                    Categories: ["gaming", "artificial-intelligence"]
                    Employees: 10
                    Revenue: 1000000;
                    Location: Beijing
                    Funding: 10000000
                    Funding Stage: early_stage; 
                    Number of Investors: 5
                    Top Investors: NVidia, Bethesda; 
                    Weekly Rank Change: 5.2
                    Monthly Rank Change: 8.8
                    Quarterly Rank Change: 2.1
                    Rank: 82687; 
                    Founders: 
                    Name: William Crowford, Degrees: University of Michigan in Computer Science, Jobs: Software Engineer at TechCo, Previous Companies: Name: GameTech, Funding: 0, Status: Inactive
                    Name: Polly Richardson, Degrees: University of Michigan in Computer Science, Jobs: Software Engineer at TechCo, Previous Companies: Name: GameTech, Funding: 0, Status: Inactive

                    UUID = 7283924-cdcb-4111-bc94-f22cd91r72e8
                    Name: Recognize
                    Description: Specialize in video and image recognition using artificial intelligence; 
                    Categories: ["image_recognition", "artificial-intelligence", "video_recognition]
                    Employees: 20; Revenue: 103001;
                    Location: San Fracisco; Funding: 1000000
                    Funding Stage: early_stage; 
                    Number of Investors: 2
                    Top Investors: Google, Invest&Co; 
                    Weekly Rank Change: 2.2
                    Monthly Rank Change: 9.0
                    Quarterly Rank Change: 1.2
                    Rank: 435133; 
                    Founders: 
                    Name: Paul Reiches, Degrees: MIT in Software Engineering, Jobs: Software Engineer at Google, Previous Companies: Name: ImageScan: Funding: 1000000, Status: Acquired by Google
                    Name: Xin Ong, Degrees: Harvard in Computer Science, Jobs: Product Manager at Meta, Previous Companies: None
                    Name: Peter Klein, Degrees: University of Stanford in Computer Science, Jobs: Software Engineer at Google, Previous Companies: None

                    UUID = 733d74b4-cdcb-4111-bc94-f22cd9gr72e8
                    Name: DataDive
                    Description: Utilizes AI to analyze and interpret complex data sets for business intelligence.
                    Categories: ["data_analysis", "artificial_intelligence"]
                    Employees: 35
                    Revenue: 2500000
                    Location: New York
                    Funding: 5000000
                    Funding Stage: seed
                    Number of Investors: 3
                    Top Investors: IBM, Sequoia Capital
                    Weekly Rank Change: 3.5
                    Monthly Rank Change: 7.1
                    Quarterly Rank Change: 4.5
                    Rank: 55689
                    Founders:
                    Name: Jessica Tao, Degrees: Columbia University in Data Science, Jobs: Data Scientist at DataWorks, Previous Companies: Name: InsightData, Funding: 0, Status: Closed
                    Name: Mark Benson, Degrees: NYU in Business Analytics, Jobs: Analyst at FinTech Solutions, Previous Companies: None

                    UUID: 733d74b4-cbcb-4f11-bc04-f22cd99e54e8
                    Name: VisionAI
                    Description: Develops cutting-edge AI algorithms for facial recognition applications.
                    Categories: ["image_recognition", "artificial_intelligence", "facial_recognition"]
                    Employees: 50
                    Revenue: 500000
                    Location: London
                    Funding: 8000000
                    Funding Stage: series_a
                    Number of Investors: 4
                    Top Investors: Intel, SoftBank
                    Weekly Rank Change: 4.2
                    Monthly Rank Change: 8.2
                    Quarterly Rank Change: 3.0
                    Rank: 98200
                    Founders:
                    Name: Alice Jordan, Degrees: Oxford in AI and Machine Learning, Jobs: Research Scientist at AI Lab, Previous Companies: Name: FaceTech, Funding: 500000, Status: Merged

                    UUID = 1s28db24-c01b-4111-bc94-f220d92872e8
                    Name: EchoSense
                    Description: Offers AI-powered solutions for sound recognition and audio analysis.
                    Categories: ["sound_recognition", "artificial_intelligence"]
                    Employees: 15
                    Revenue: 760000
                    Location: Berlin
                    Funding: 2000000
                    Funding Stage: early_stage
                    Number of Investors: 2
                    Top Investors: Amazon, Deutsche Telekom
                    Weekly Rank Change: 1.8
                    Monthly Rank Change: 5.5
                    Quarterly Rank Change: 2.7
                    Rank: 235487
                    Founders:
                    Name: Julian Schmidt, Degrees: Technical University of Berlin in Sound Engineering, Jobs: Audio Engineer at SoundWave, Previous Companies: None

                    UUID = 1sjd9224-c01b-4111-bc94-f22019snh2e8
                    Name: HealthAI
                    Description: Uses artificial intelligence to predict and diagnose health conditions from medical imaging.
                    Categories: ["healthcare", "artificial_intelligence", "medical_imaging"]
                    Employees: 40
                    Revenue: 3200000
                    Location: Boston
                    Funding: 15000000
                    Funding Stage: series_b
                    Number of Investors: 5
                    Top Investors: Merck, Johnson & Johnson
                    Weekly Rank Change: 6.0
                    Monthly Rank Change: 10.3
                    Quarterly Rank Change: 5.1
                    Rank: 30456
                    Founders:
                    Name: Dr. Emily Stone, Degrees: Harvard Medical School, Jobs: Radiologist at Boston Medical Center, Previous Companies: None

                    UUID = 31sjd9224-c01b-4111-bc94-f220d92872e8
                    Name: AgriGrow
                    Description: Employs AI for precision farming, enhancing crop yield predictions and soil health.
                    Categories: ["agriculture", "artificial_intelligence"]
                    Employees: 25
                    Revenue: 1200000
                    Location: San Jose
                    Funding: 3000000
                    Funding Stage: seed
                    Number of Investors: 3
                    Top Investors: Bayer, Syngenta
                    Weekly Rank Change: 2.3
                    Monthly Rank Change: 6.7
                    Quarterly Rank Change: 3.9
                    Rank: 75632
                    Founders:
                    Name: Carlos Mendez, Degrees: UC Davis in Plant Sciences, Jobs: Agronomist at GreenFields, Previous Companies: None

                    UUID: 1sjd1224-c01b-4111-bc94-f220d92872e8; Name: AIProve; Description: Provides AI-driven solutions for automated testing and quality assurance; Categories: ["software-testing", "artificial-intelligence"]; Employees: 15; Revenue: 500000; Location: Austin; Funding: 2500000; Funding Stage: seed; Number of Investors: 3; Top Investors: TechStart, AngelHub; Weekly Rank Change: 3.4; Monthly Rank Change: 7.1; Quarterly Rank Change: 3.5; Rank: 122134; Founders: Name: Sarah Jenkins, Degrees: Carnegie Mellon University in Software Engineering, Jobs: Quality Assurance Manager at SoftDev, Previous Companies: Name: QualityFirst, Funding: 0, Status: Inactive.

                    UUID: 1sjd9224-c01b-4111-bc94-f220d92872e8; Name: SecureAI; Description: Advanced AI image and object recognition for security systems; Categories: ["image_recognition", "security", "artificial-intelligence"]; Employees: 30; Revenue: 2000000; Location: London; Funding: 5000000; Funding Stage: Series A; Number of Investors: 4; Top Investors: SecureTech Ventures, AI Fund; Weekly Rank Change: 4.6; Monthly Rank Change: 12.3; Quarterly Rank Change: 6.7; Rank: 97856; Founders: Name: Michael O'Donnell, Degrees: University of Edinburgh in AI and Robotics, Jobs: Security Analyst at CyberNet, Previous Companies: None.

                    UUID: 87274299-10hfbs-189h9-1h82-hubfhsj; Name: DeepLearn; Description: Specializes in developing deep learning models for natural language processing; Categories: ["natural_language_processing", "artificial-intelligence", "deep_learning"]; Employees: 22; Revenue: 750000; Location: Berlin; Funding: 3000000; Funding Stage: seed; Number of Investors: 3; Top Investors: EuroTech, BerlinAI; Weekly Rank Change: 1.9; Monthly Rank Change: 8.5; Quarterly Rank Change: 2.4; Rank: 155432; Founders: Name: Emma Hart, Degrees: Technical University of Munich in Computational Linguistics, Jobs: Data Scientist at DataWorks, Previous Companies: None.

                    UUID: 1sjd9224-c01b-4111-b1904-f220d92872e8; Name: SynthGen; Description: Creates synthetic data for training AI models in various sectors; Categories: ["synthetic_data", "data_science", "artificial-intelligence"]; Employees: 18; Revenue: 300000; Location: Toronto; Funding: 2000000; Funding Stage: seed; Number of Investors: 2; Top Investors: AI Ventures, NorthStar; Weekly Rank Change: 2.7; Monthly Rank Change: 6.4; Quarterly Rank Change: 4.3; Rank: 207655; Founders: Name: Leonard McCoy, Degrees: University of Toronto in Data Science, Jobs: Research Scientist at BigData, Previous Companies: Name: DataLab, Funding: 50000, Status: Merged.

                    UUID: 9abuia224-c01b-4111-bc94-f210d2872e8; Name: CodeIntelli; Description: Leveraging AI to automate coding and software development processes; Categories: ["software_development", "automation", "artificial-intelligence"]; Employees: 25; Revenue: 1200000; Location: New York; Funding: 4500000; Funding Stage: Series A; Number of Investors: 5; Top Investors: SoftBank, CodeWorks; Weekly Rank Change: 5.9; Monthly Rank Change: 11.4; Quarterly Rank Change: 5.1; Rank: 88321; Founders: Name: Raj Patel, Degrees: Stanford University in Computer Science, Jobs: Software Engineer at TechSolutions, Previous Companies: None.

                    UUID: 99hdu224-c01b-4111-bc94-f210d2872e8; Name: ImageMind; Description: AI-powered platform for enhancing and analyzing digital images; Categories: ["image_processing", "artificial-intelligence", "digital_media"]; Employees: 20; Revenue: 800000; Location: Seoul; Funding: 2200000; Funding Stage: seed; Number of Investors: 2; Top Investors: MediaTech, Visionary; Weekly Rank Change: 6.2; Monthly Rank Change: 13.7; Quarterly Rank Change: 7.8; Rank: 102657; Founders: Name: Hye-Jin Kim, Degrees: KAIST in Computer Vision, Jobs: Image Analyst at PixelPlus, Previous Companies: None.

                    UUID: 1eoihdu224-c01b-4111-bc94-f210d2872e8
                    Name: DataDeep
                    Description: Data analytics firm leveraging AI to provide deep insights into big data.
                    Categories: ["data-analytics", "artificial-intelligence"]
                    Employees: 50
                    Revenue: 5000000
                    Location: New York
                    Funding: 15000000
                    Funding Stage: series_a
                    Number of Investors: 3
                    Top Investors: Sequoia Capital, Y Combinator
                    Weekly Rank Change: 3.5
                    Monthly Rank Change: 7.5
                    Quarterly Rank Change: 4.2
                    Rank: 55687
                    Founders:
                    Name: Sophia Martins, Degrees: Cornell University in Data Science, Jobs: Data Scientist at IBM, Previous Companies: None

                    UUID: 9910ie9924-c01b-4111-bc94-f210d2872e8
                    Name: VisionaryAI
                    Description: Developing cutting-edge facial recognition software using artificial intelligence.
                    Categories: ["image_recognition", "artificial-intelligence", "facial_recognition"]
                    Employees: 30
                    Revenue: 2000000
                    Location: Los Angeles
                    Funding: 8000000
                    Funding Stage: seed
                    Number of Investors: 4
                    Top Investors: Andreessen Horowitz, Techstars
                    Weekly Rank Change: 4.0
                    Monthly Rank Change: 10.0
                    Quarterly Rank Change: 5.1
                    Rank: 112233
                    Founders:
                    Name: Alex Jensen, Degrees: UCLA in Computer Science, Jobs: Engineer at Snap Inc., Previous Companies: None

                    UUID: 99hdu224-c01b-4111-bc94-f188qdhq2e8
                    Name: EchoTech
                    Description: EchoTech pioneers in echo location technologies for navigation and mapping with AI.
                    Categories: ["navigation", "artificial-intelligence", "mapping"]
                    Employees: 15
                    Revenue: 750000
                    Location: Boston
                    Funding: 2500000
                    Funding Stage: pre_seed
                    Number of Investors: 1
                    Top Investors: Local angel investor
                    Weekly Rank Change: 1.8
                    Monthly Rank Change: 6.4
                    Quarterly Rank Change: 3.3
                    Rank: 96533
                    Founders:
                    Name: Rita Kozlov, Degrees: MIT in Electrical Engineering, Jobs: Research Scientist at NASA, Previous Companies: None

                    UUID: 9989qbh224-c01b-4111-bc94-f210d2872e8
                    Name: DeepSightAI
                    Description: Specializes in AI-powered surveillance systems with real-time video analytics.
                    Categories: ["image_recognition", "artificial-intelligence", "surveillance"]
                    Employees: 40
                    Revenue: 3100000
                    Location: London
                    Funding: 12000000
                    Funding Stage: series_a
                    Number of Investors: 6
                    Top Investors: Balderton Capital, Accel Partners
                    Weekly Rank Change: 6.1
                    Monthly Rank Change: 11.5
                    Quarterly Rank Change: 6.7
                    Rank: 33789
                    Founders:
                    Name: Jamal Yunos, Degrees: Imperial College London in AI, Jobs: AI Researcher at DeepMind, Previous Companies: None

                    UUID: 99n11jen924-c01b-4111-bc94-f210d2872e8
                    Name: GenieAI
                    Description: AI platform offering personalized content recommendations using machine learning.
                    Categories: ["machine_learning", "artificial-intelligence", "content_recommendation"]
                    Employees: 25
                    Revenue: 1200000
                    Location: Toronto
                    Funding: 5000000
                    Funding Stage: seed
                    Number of Investors: 2
                    Top Investors: Shopify, AngelList
                    Weekly Rank Change: 2.9
                    Monthly Rank Change: 8.1
                    Quarterly Rank Change: 3.9
                    Rank: 50987
                    Founders:
                    Name: Elena Vasquez, Degrees: University of Toronto in Computer Science, Jobs: Software Developer at Shopify, Previous Companies: None

                    UUID: 991buidqb-c01b-4111-bc94-f210d2872e8; Name: AI Genesis; Description: Pioneers in creating AI-driven solutions for healthcare diagnostics; Categories: ["healthcare", "artificial-intelligence"]; Employees: 50; Revenue: 5000000; Location: Boston; Funding: 20000000; Funding Stage: early_stage; Number of Investors: 3; Top Investors: MedTech Innovate, HealthAI Ventures; Weekly Rank Change: 3.5; Monthly Rank Change: 7.1; Quarterly Rank Change: 4.3; Rank: 34567; Founders: Name: Sarah Tan, Degrees: Johns Hopkins University in Biomedical Engineering, Jobs: Research Scientist at MedSolutions, Previous Companies: Name: HealthTrack, Funding: 500000, Status: Acquired by MedTech Innovate

                    UUID: 99hdu224-c011niow-u829n-f210d2872e8; Name: Visionary Robotics; Description: Developing next-generation AI-powered robots for industrial automation; Categories: ["robotics", "artificial-intelligence", "industrial"]; Employees: 70; Revenue: 8000000; Location: Munich; Funding: 15000000; Funding Stage: Series A; Number of Investors: 4; Top Investors: RoboGlobal, AI Fund; Weekly Rank Change: 4.7; Monthly Rank Change: 5.6; Quarterly Rank Change: 6.2; Rank: 22654; Founders: Name: Max Zimmer, Degrees: Technical University of Munich in Mechanical Engineering, Jobs: Lead Engineer at AutoRobo, Previous Companies: Name: RoboCraft, Funding: 0, Status: Inactive

                    UUID: 1najk4-c01b-4111-bc94-f210d2872e8; Name: DeepThink; Description: AI startup focusing on deep learning algorithms for financial forecasting; Categories: ["financial-technology", "artificial-intelligence"]; Employees: 30; Revenue: 3000000; Location: New York; Funding: 8000000; Funding Stage: seed; Number of Investors: 2; Top Investors: FinTech Innovators, Quantum Capital; Weekly Rank Change: 2.8; Monthly Rank Change: 10.0; Quarterly Rank Change: 3.7; Rank: 54576; Founders: Name: Elena Morris, Degrees: Columbia University in Financial Engineering, Jobs: Quantitative Analyst at Wall Street, Previous Companies: Name: QuantPredict, Funding: 0, Status: Inactive

                    UUID: bdub1-nunfi11b-4111-bc94-f210d2872e8; Name: ClearView AI; Description: Offers cutting-edge AI technologies for enhancing security systems through facial recognition; Categories: ["security", "artificial-intelligence", "image_recognition"]; Employees: 40; Revenue: 4000000; Location: London; Funding: 12000000; Funding Stage: Series A; Number of Investors: 3; Top Investors: Security First, AI Global; Weekly Rank Change: 6.2; Monthly Rank Change: 11.4; Quarterly Rank Change: 5.0; Rank: 56789; Founders: Name: Michael Kingston, Degrees: Imperial College London in Computer Science, Jobs: Security Analyst at SecureTech, Previous Companies: Name: FaceGuard, Funding: 200000, Status: Acquired by Security First

                    UUID: bdub1-nunfi11b-112e-bc94-f210d2872e8; Name: AutoCode AI; Description: Innovating the field of software development with AI-driven code generation and analysis; Categories: ["software", "artificial-intelligence"]; Employees: 25; Revenue: 2000000; Location: Bangalore; Funding: 5000000; Funding Stage: early_stage; Number of Investors: 2; Top Investors: CodeVentures, DevTech Fund; Weekly Rank Change: 1.9; Monthly Rank Change: 8.2; Quarterly Rank Change: 2.8; Rank: 78901; Founders: Name: Priya Anand, Degrees: Indian Institute of Technology Bombay in Computer Science, Jobs: Software Developer at TechInnovate, Previous Companies: Name: DevStream, Funding: 0, Status: Inactive

                    UUID: bdub1-nu1e11b-4111-bc94-f210d2872e8; Name: EchoAI; Description: Specializes in AI-based audio recognition and processing for smart home devices; Categories: ["smart_home", "artificial-intelligence", "audio_recognition"]; Employees: 35; Revenue: 2500000; Location: Seoul; Funding: 7000000; Funding Stage: Series A; Number of Investors: 3; Top Investors: SmartLife VC, EchoInnovate; Weekly Rank Change: 5.6; Monthly Rank Change: 12.3; Quarterly Rank Change: 6.7; Rank: 90234; Founders: Name: Jun-seo Kim, Degrees: Seoul National University in Electrical Engineering, Jobs: Audio Engineer at SoundTech, Previous Companies: Name: SoundWave, Funding: 300000, Status: Acquired by SmartLife VC

                    UUID: b81yb-1bh11b-4111-bc94-f210d2872e8
                    Name: AI Nexus
                    Description: A hub for connecting AI startups with potential investors and partners, focusing on innovative AI solutions.
                    Categories: ["artificial-intelligence", "networking", "startups"]
                    Employees: 15
                    Revenue: 250000
                    Location: New York
                    Funding: 5000000
                    Funding Stage: seed
                    Number of Investors: 3
                    Top Investors: Sequoia Capital, AngelList
                    Weekly Rank Change: 4.5
                    Monthly Rank Change: 7.3
                    Quarterly Rank Change: 3.4
                    Rank: 109234
                    Founders:
                    Name: Emily Zhao, Degrees: Columbia University in Business and AI, Jobs: Venture Capitalist at SeedFund, Previous Companies: Name: StartUpConnect, Funding: 0, Status: Inactive
                    Name: Marcus Duarte, Degrees: NYU in Computer Science, Jobs: Software Engineer at AI Tech, Previous Companies: None

                    UUID: 1e1hjd-i11b-4111-bc94-f210d2872e8
                    Name: SightAI
                    Description: Develops cutting-edge AI-driven image recognition systems for security and surveillance.
                    Categories: ["image_recognition", "security", "artificial-intelligence"]
                    Employees: 50
                    Revenue: 5000000
                    Location: London
                    Funding: 20000000
                    Funding Stage: series_a
                    Number of Investors: 4
                    Top Investors: Intel, SoftBank
                    Weekly Rank Change: 6.0
                    Monthly Rank Change: 11.1
                    Quarterly Rank Change: 5.5
                    Rank: 25678
                    Founders:
                    Name: Alisha Kaur, Degrees: Imperial College London in AI, Jobs: Security Analyst at CyberSec, Previous Companies: Name: SecureNet, Funding: 500000, Status: Active
                    Name: Tomás Rivera, Degrees: University of Cambridge in Computer Science, Jobs: CTO at LockSafe, Previous Companies: None

                    UUID: bdub1-nunfi11b-4dahb181-e2y277217
                    Name: DeepLearn
                    Description: Offers online courses and resources for learning advanced AI and machine learning techniques.
                    Categories: ["education", "machine_learning", "artificial-intelligence"]
                    Employees: 35
                    Revenue: 750000
                    Location: Bangalore
                    Funding: 3000000
                    Funding Stage: seed
                    Number of Investors: 2
                    Top Investors: Udemy, Coursera
                    Weekly Rank Change: 3.6
                    Monthly Rank Change: 6.4
                    Quarterly Rank Change: 2.8
                    Rank: 82647
                    Founders:
                    Name: Priya Desai, Degrees: IIT Bombay in Computer Science, Jobs: Data Scientist at DataWorks, Previous Companies: Name: EduAI, Funding: 0, Status: Merged
                    Name: Jordan Michaels, Degrees: Stanford University in AI, Jobs: Instructor at CodeAcademy, Previous Companies: None

                    UUID: 1811bdub1-nunfi11b-4111-bc94-f210d2872e8
                    Name: Botify
                    Description: Specializes in creating personalized chatbots for businesses, using natural language processing.
                    Categories: ["natural_language_processing", "chatbots", "business_services"]
                    Employees: 40
                    Revenue: 2000000
                    Location: Toronto
                    Funding: 8000000
                    Funding Stage: series_a
                    Number of Investors: 3
                    Top Investors: Shopify, Twilio
                    Weekly Rank Change: 5.7
                    Monthly Rank Change: 10.2
                    Quarterly Rank Change: 4.1
                    Rank: 54322
                    Founders:
                    Name: Leo Schmidt, Degrees: University of Toronto in Computer Science, Jobs: Developer at Shopify, Previous Companies: Name: ChatTech, Funding: 0, Status: Inactive
                    Name: Sofia Alvarez, Degrees: McGill University in AI, Jobs: AI Researcher at AI Lab, Previous Companies: None

                    A: I used the evaluation criteria to choose the following top 10 companies. While many companies focus on AI, not many focus on image recognition,
                    so these are the ones chosen as they relate most to the query. The output is in descending order (best at the top):
                    
                    1) VisionAI; UUID = 733d74b4-cbcb-4f11-bc04-f22cd99e54e8 - the company develops AI algorithms for facial recognition, which relates to the query. The founder has an excellent education, and a great previous job and founded company.
                    2) Recognize; UUID = 7283924-cdcb-4111-bc94-f22cd91r72e8 - the mention of video and image recognition using artificial intelligence relates to the query. The founders attended good universities, and one has great entrepeneurial success. Their location is in the US, which is good.
                    3) SecureAI; UUID = 1sjd9224-c01b-4111-bc94-f220d92872e8 - they focus on image recognition for security solutions, their tech is similar to the query. The company rank is quite high, the founder has a good education and they have high-value investors.
                    ...
                    10) ImageMind; UUID = 99hdu224-c01b-4111-bc94-f210d2872e8 - their use of AI to enhance digital images implies a focus on image recognition. Their founders have not as good education as the higher rankings.
                    In this case, we output [3,1,8,...,12] because those are the positions of the choices we make here.

                    If we chose different positions, those would be the ones we output.
                    """ + "Q: The query is: " + query + "\nThe companies are:\n" + company_info + """
                    \n Let's think about this step by step, and have a good reason according to the evaluation points for each choice. 
                    We MUST return the indices of our choices made, in a clear list at the end of our response. 
                    We also MUST return some good reasons for each company we chose, and we cannot make up anything about any of the companies.
                    All information in the evaluation must come from the information we have been given, nothing can be made up."""
            }
        ]
        response = client.chat.completions.create(model="gpt-4-turbo-preview", messages=messages)
        return response.choices[0].message.content
    
    #Perform ToT when in expensive mode
    if EXPENSIVE_MODE:

        messages = [
            {
                "role": "system",
                "content":
                    """You are a helpful assistant that is able to evaluate a list of companies that relate to a query. 
                    You can perform a thought to acquire an evaluation of the companies. You should think at least 5 times.
                    After thinking, you will have the evaluations of certain companies, at which stage, you should choose the 10
                    that relate most to the query. 
                    You should call the 5 thoughts as 5 separate functions, and this should be done in your first step of thinking.
                    Your initial output should be the 5 functions calls.
                    """
            },
            {
                "role": "user",
                "content": "You should call thought() 5 times to perform thoughts. Don't output until you have completed the thoughts. The query to relate the evaluations to is: " + query + """
                ; The company information should not be evaluated here, but is provided so you can ensure that evaluations are correct. The company
                information is as follows: """ + company_info
            }
        ]

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "thought",
                    "description": """
                    Perform an evaluation of the companies. Return the indices of the chosen companies along with an evaluation.
                    In each evaluation, include the name of the company. Ensure that it is clear which evaluation relates to each company,
                    include the name of the company in each evaluation.
                    """
                }
            }
        ]

        #TODO rare bug where the LLM tries to call a function called multi_tool_use.parallel that doesn't exist - maybe fixed?
        response = client.chat.completions.create(model="gpt-4-turbo-preview", messages=messages, tools=tools, tool_choice="auto",)
        response_message = response.choices[0].message
        tool_calls = response_message.tool_calls
        messages.append(response_message)  #extend conversation with assistant's reply
        if tool_calls:
            for tool_call in tool_calls:
                single_thought = thought()
                messages.append(
                    {
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": "thought",
                    "content": single_thought,
                    }
                )

        messages.append(
            {
                "role": "user",
                "content": 
                """
                Now that you have done the thoughts, you must return the list of the 10 indicess of companies that relate most to the query via their evaluations.
                You should include an evaluation with each explaining why they seemed the most relevant to the query, and why you chose them.
                Put the list of indices clearly at the end. Do not perform any more thoughts! Let's think about this step by step, and have a good reason for each choice.
                You should order the companies from best to worst, e.g. if company at index 42 is the most relevant to the query and appears most in the thoughts,
                and company 3 is the 10th most relevant company appearing in the thoughts, then the output is [42, ... , 3]. Do this for the companies you have chosen.
                Do not make up any facts about the companies."""
            }
        )

        #TODO right now, sometimes the LLM decides there isn't enough information to perform an evaluation
        #TODO This won't be an issue when more information is found on each company

        #TODO I think sometimes the LLM makes up some of the evaluation points, especially about the founder backgrounds. I expect this
        #TODO to disappear once the founder backgrounds are included properly, but something to beware of 
        response = client.chat.completions.create(model="gpt-4-turbo-preview", messages=messages, tools=tools, tool_choice = "auto")

        eval = response.choices[0].message.content

        #output evaluations if testing
        if TESTING:
            with open(f"sourcing/evaluations/eval{query[0]}.txt", "w") as file:
                file.write(eval)

        return eval
    
    else: #not expensive mode, just do a single thought
        return thought()

# Function that takes a list of companies, each with their relevant company information and outputs the necessary information about each one
# Input data contains all information
# Much more could be returned right now
def outputCompanies(companies, indices, evaluations):
    #TODO sometimes the the wrong companies are output here, maybe because of the indices?
    #TODO I advise someone with more knowledge of pandas try to fix this, currently sometimes the evaluations don't match the companies
    selected_companies = companies.iloc(indices)    

    outputLines = []
    outputLines.append("\n------------------------------------------------------------\n")
    count=0
    for i, row in selected_companies.iterrows():
        outputLines.append(f"{count+1}.\nName: {row['company']}\nWebsite: {row['website']}\nLocation: {row['location']}\nDescription: {row['description']}\nFounders: {row['founder_names']}\nFunding: {row['funding']}\nReason: {evaluations[count]}\n")
        outputLines.append("------------------------------------------------------------\n")
        count+=1

    return outputLines

# LLM that controls the flow of the program. Uses a crew of LLMs to decide what tools to use, 
# complete different parts of the procedure, etc
# Always runs in 6 sections:
# 1) Pre-search preparation
# 2) Searching for companies
# 3) Refinement of searches
# 4) Pre-ranking preparation
# 5) Ranking companies
# 6) Outputting companies
def controller(query):
    #define initial messages. These start off as a CoT ReAct Query
    messages = [
                {"role": "system", 
                 "content": 
                    """
                    You are a helpful assistant that takes an input query which is a description of a company. 
                    Your job is to find the top 10 companies related to this query.
                    You will do this in 6 stages:
                    1) Get all information needed to search the web, e.g. get the crunchbase categories related to the query so we can search crunchbase
                    2) Search the web for all of the companies relating to the query, e.g. search crunchbase using the categories we just obtained. You cannot do this at the same time as finding the categories.
                    3) Refine the set of companies down to around 100 using the information found and the query
                    4) Find all information relevant to our final 100 companies, including founder backgrounds
                    5) Rank the top 10 companies using all of the information found and the query. Recieve a list of 10 evaluations, and 10 indices of companies.
                    6) Output the companies with all necessary information
                    """
                },
                {"role": "user", 
                 "content": 
                    """
                    Q: Tell me the top 10 blockchain investment companies
                    A: 
                    Thought 1: I need to get all information needed to search the web. I will be searching crunchbase to find the companies.
                    To search crunchbase, I need the categories to search for that relate to the query. I cannot search crunchbase yet. 
                    I should only search for a category once, and use the important part of the query for the search.
                    Act 1: chooseCategory("blockchain investment companies")
                    Observation 1: I now have the categories - ["blockchain-investment", "cryptocurrency"]

                    Thought 2: I need to perform a search for companies related to the query. I will be searching crunchbase for this. 
                    I have the categories to search for. I want to search for all of the companies related to these categories.
                    Act 2: searchCrunchbaseCompanies(categories = ["blockchain-investment", "cryptocurrency"], n=-1)
                    Observation 2: 1971 companies found

                    Thought 3: I have all of the companies, but I need to refine this down to 100.
                    Act 3: refine("blockchain investment companies", n=100)
                    Observation 3: 100 companies remaining.

                    Thought 4: I need to find the more detailed information on each of the 100 remaining companies. I should find the 
                    information about the background of each founder.
                    Act 4: searchCrunchbaseFounders()
                    Observation 4: Founder backgrounds have been located.

                    Thought 5: Now that I have the more in depth information, I need to rank each of the companies to find the top 10. 
                    Act 5: rank("blockchain investment companies", n=10)
                    Observation 5: The top 10 companies have indices [54,13,91,1,2,74,12,90,53,19]. 
                    The reasons for each one are as follows:
                    - This company has a high rank on crunchbase, and is a blockchain investment company
                    - They perform research into blockchain technology and invest in cryptocurrency
                    ...
                    - They have founders with valuable backgrounds and invest in blockchain technology.

                    Thought 6: I have the top 10 companies, I just need to output them. I need to input the indices array which is at
                    the end of the previous message. I also need to input the evaluations array which is within the previous message.
                    There should be the same number of evaluations and indices, both 10.
                    Act 6: outputCompanies(indices = [54,13,91,1,2,74,12,90,53,19], evaluations = ["This company has a high rank on crunchbase, and is a blockchain investment company",
                    "They perform research into blockchain technology and invest in cryptocurrency", 
                    ...
                    "They have founders with valuable backgrounds and invest in blockchain technology."])
                    Observation 6: Outputting finished. Task complete.

                    Q: Give me the top 10 indie game development companies
                    A:
                    Thought 1: I need to get all information needed to search the web. I will be searching crunchbase to find the companies.
                    To search crunchbase, I need the categories to search for that relate to the query. I should only try to choose a single list
                    of categories, so I should call chooseCategory only once, using the key information from the query.
                    Act 1: chooseCategory("indie game development")
                    Observation 1: I now have the categories - ["gaming", "game-development"]

                    Thought 2: I need to perform a search for companies related to the query. I will be searching crunchbase for this. 
                    I have the categories to search for. I want to search for all of the companies related to these categories, so I will choose n=-1.
                    Act 2: searchCrunchbaseCompanies(categories = ["gaming", "game-development"], n=-1)
                    Observation 2: 2817 companies found. 

                    Thought 3: I have all of the companies, but I need to refine this down to 100.
                    Act 3: refine("indie game development, n=100")
                    Observation 3: 100 companies remaining.

                    Thought 4: I need to find the more detailed information on each of the 100 remaining companies. I should find the 
                    information about the background of each founder.
                    Act 4: searchCrunchbaseFounders()
                    Observation 4: Founder backgrounds have been located.

                    Thought 5: Now that I have the more in depth information, I need to rank each of the companies to find the top 10. 
                    Act 5: rank("indie game development", n=10)
                    Observation 5: The top 10 companies have the indices [2,1,23,56,75,35,64,24,78,58]
                    The reasons are:
                    - This company has been very successful recently, and their founders are based in LA.
                    - They have made many successful indie games
                    ...
                    - The founders live in LA, and they have high-value investors

                    Thought 6: I have the top 10 companies, I just need to output them. I must input the list of indices which was
                    included in the previous message. This is one variable. The other variable is the list of evaluations. This
                    was also in the previous message. I should make sure that I have 10 evaluations and 10 indices, in separate variables.
                    Act 6: outputCompanies(indices = [2,1,23,56,75,35,64,24,78,58], evaluations = ["This company has been very successful recently, and their founders are based in LA.",
                    "They have made many successful indie games", ... "The founders live in LA, and they have high-value investors"])
                    Observation 6: Outputting finished. Task complete.
        
                    Q: 
                    """ + query
                }
            ]
    
    #define our functions to call
    tools = [
        {
            "type": "function",
            "function": {
                "name": "searchCrunchbaseCompanies",
                "description": "Search for companies in certain categories on crunchbase",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "categories": {
                            "type": "array",
                            "items": {
                                "type": "string",
                            },
                            "description": "a list of crunchbase categories to be searched"
                        },
                        "n": {
                            "type": "number",
                            "description": "number of results for search to return. input -1 to find all companies"
                        }
                    },
                    "required": [
                        "categories",
                        "n"
                    ]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "searchCrunchbaseFounders",
                "description": "Search for founders backgrounds on crunchbase",
            }
        },
        {
            "type": "function",
            "function": {
                "name": "refine",
                "description": "takes a large list of companies and chooses only the ones that are most relevant to a query",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "n": {
                            "type": "number",
                            "description" : "the number of companies that we want remaining after refinement"
                        },
                        "query" : {
                            "type": "string",
                            "description": "the description of a company that we are comparing each of our found companies to"
                        }
                    },
                    "required": [
                        "n",
                        "query"
                    ]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "chooseCategory",
                "description": "takes a description of a company and returns some categories that can be searched on crunchbase",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "short description of a company"
                        }
                    },
                    "required": [
                        "query"
                    ]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "rank",
                "description": "rank the top 10 companies based on the found information. outputs the uuids list and the evaluations list, these are to be inputted to the output function",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "the initial query that was asked, that we should be ranking the companies on"
                        },
                        "n":{
                            "type": "number",
                            "description": "the number of companies that should be in the top ranking"
                        }
                    }
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "outputCompanies",
                "description": "takes a set of companies and their detailed information, along with a list of their indices, and outputs the website URL, name, description, founders and their background, funding and its background for each company at an index stored in indices within the dataframe",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "indices": {
                            "type": "array",
                            "items": {
                                "type": "integer",
                                "description": "the index of one of the companies within the datafram"
                            },
                            "description": "the list of indices of the companies to be outputted"
                        },
                        "evaluations": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "description": "an evaluation of a company"
                            },
                            "description": "the list of evaluations of companies that was returned from ranking the companies"
                        }
                    },
                    "required": [
                        "indices",
                        "evaluations"
                    ]
                }
            }
        },
        
        
    ]

    #this stores the very large arguments that we don't want to keep passing to the LLM e.g. 100 companies and all their data
    local_args = {} 

    for stage in range(1,7):
        #allow LLM to think about messages up to this stage
        response = client.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )
        response_message = response.choices[0].message

        #check for function calls at this stage
        tool_calls = response_message.tool_calls
        if tool_calls: #if there was a function call
            #TODO error handling for invalid JSONs - in all my testing, no invalid JSONs have appeared but may be wise to implement anyway
            messages.append(response_message)  #extend conversation with assistant's reply

            # for each function call, we run the function
            for tool_call in tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)

                #choose the correct function to call, and update variables where necessary
                match function_name:

                    case "searchCrunchbaseCompanies":
                        #add the companies to the local arguments
                        print("Searching for companies on Crunchbase...")
                        #TODO there is a bug where this can be called on stage 1, and it guesses categories - maybe fixed?
                        #try statement to catch this bug
                        try:
                            #LLM chooses n=-1 when we want to search all of them. Right now, I expect it chooses this every time, but this can be changed
                            local_args.update({"crunchbase_companies": searchCrunchbaseCompanies(function_args["categories"], function_args["n"])})
                            function_response = str(local_args["crunchbase_companies"].shape[0]) + " companies found."
                        except:
                            function_response = "Crunchbase Error - maybe LLM searched too early, or network is down?"
                        print(function_response)
            
                    case "searchCrunchbaseFounders": 
                        print("Searching for founders on Crunchbase... [CURRENTLY BROKEN]")

                        #TODO most crunchbase founders don't have their degree info on there, so this is currently non-functional
                        #TODO replace this with your searching for founder function, maybe one for expensive mode and one for the cheap mode
                        local_args["refined_companies"]["founder_backgrounds"] = local_args["refined_companies"]["founder_names"]

                        #old code that searches crunchbase, but not enough info on there
                        #f = local_args["refined_companies"]["founder_uuids"] 
                        #local_args["refined_companies"]["founder_background"] = f.apply(lambda x: founderBackgrounds(x))

                        function_response = "Founder backgrounds have been located"

                    case "refine":
                        print("Refining Search...")
                        local_args.update({"refined_companies": refine(local_args["crunchbase_companies"], function_args["query"], function_args["n"])})
                        function_response = str(local_args["refined_companies"].shape[0]) + " remaining"

                    case "chooseCategory":
                        print("Choosing categories...")
                        function_response = str(chooseCategory(function_args["query"]))

                    case "rank":
                        print("Ranking companies...")
                        function_response = rank(local_args["refined_companies"], function_args["query"], function_args["n"])

                    case "outputCompanies":
                        print("Outputting companies...")
                        result = outputCompanies(local_args["refined_companies"], function_args["indices"], function_args["evaluations"])
                        function_response = "Outputting finished. Task complete."
                        #if we are using the testing rig
                        if TESTING:
                            return result

                #add the necessary function response to the messages for the next conversation
                messages.append(
                    {
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": function_response,
                    }
                )  
                
def testing():
    #set of queries that we want to test {topic: query}
    tests = {"AI_agent": "Find all AI agent frameworks and AI agent developer tool startups"}
    for test in tests:
        q = tests[test]
        result = controller(q)

        messages = [
            {
                "role": "system",
                "content": 
                    """
                    You are a helpful assistant. Your job is to take an input of a query that is used for finding companies that match the query,
                    as well as the companies that have been returned by this query, and you must rank the relevance and quality of the companies chosen.
                    You should rank each choice on a scale of 1-10, and the ranking should be based on the relevance of the company to the query.
                    When you have created the rankings, you should call the function output with an input of the list of rankings. Ensure that the list is 
                    in the same order as the companies that were input.
                    """
            },
            {
                "role": "user",
                "content":
                    """
                    Query: Find the top 10 companies that create video games that are working on action and shooter games.
                    Companies:
                    ------------------------------------------------------------

                    1.
                    Name: Certain Affinity
                    Website: http://www.certainaffinity.com/
                    Description: The goal of creating innovative, top-quality action games.
                    Founders: Max Hoberman
                    Funding: 15000000

                    ------------------------------------------------------------

                    2.
                    Name: Blind Squirrel Games
                    Website: http://blindsquirrelentertainment.com
                    Description: Blind Squirrel Games is a computer games company specializing in video game development services.
                    Founders: Brad Hendricks
                    Funding: 5000000

                    ------------------------------------------------------------

                    3.
                    Name: ProbablyMonsters
                    Website: http://www.probablymonsters.com
                    Description: ProbablyMonsters builds AAA video game studios and interactive entertainment.
                    Founders: Harold Ryan
                    Funding: 218800000

                    ------------------------------------------------------------

                    4.
                    Name: SuperTeam Games
                    Website: https://www.superteamgames.com/
                    Description: SuperTeam Games is is creating a new breed of sports games.
                    Founders: Not found
                    Funding: 10000000

                    ------------------------------------------------------------

                    5.
                    Name: Redhill Games
                    Website: https://www.redhillgames.com/
                    Description: Redhill Games are a free to play PC game studio formed by a team of industry veterans.
                    Founders: Milos Jerabek
                    Funding: 30000000

                    ------------------------------------------------------------

                    6.
                    Name: Phoenix Labs
                    Website: https://phxlabs.ca
                    Description: Phoenix Labs crafts a new AAA multiplayer experience for players to create lasting, memorable relationships for years to come.   
                    Founders: Jesse Houston,Robin Mayne,Sean Bender
                    Funding: 3518500

                    ------------------------------------------------------------

                    7.
                    Name: Shrapnel
                    Website: https://www.shrapnel.com/
                    Description: Shrapnel is an AAA Extraction FPS powered by next-gen community-driven tools, built on the blockchain to offer true ownership.   
                    Founders: Calvin Zhou,Edmund Shern,Herbert Taylor,Mark Long,Naomi Lackaff
                    Funding: 20600000

                    ------------------------------------------------------------

                    8.
                    Name: Velan Studios
                    Website: http://www.velanstudios.com
                    Description: Velan Studios is a new development studio made up of a diverse team of game industry veterans.
                    Founders: Karthik Bala
                    Funding: 7000000

                    ------------------------------------------------------------

                    9.
                    Name: Singularity 6
                    Website: https://www.singularity6.com
                    Description: Singularity 6 is a game development studio dedicated to the idea that games can create deeper, more meaningful experiences.      
                    Founders: Aidan Karabaich,Anthony Leung
                    Funding: 49000000

                    ------------------------------------------------------------

                    10.
                    Name: Mythical Games
                    Website: https://mythicalgames.com
                    Description: Mythical Games is a video game engine for player-owned economies.
                    Founders: Cameron Thacker,Chris Downs,Jamie Jackson,Rudy Koch
                    Funding: 297000000

                    ------------------------------------------------------------

                    Thinking:
                    1) The first company, Certain Affinity, is a game development company, and they specifically say that they work on high-quality action games. This
                    is included in the query, so is very relevant. They might make shooter games, but they don't specify, so I can't rank them on that. They have
                    a lot of funding too, so are probably a high quality company. The ranking is 8.3.
                    2) Blind Squirrel games is a game development company, with a small amount of funding. There isn't much else that makes this relevant
                    to the query, so the ranking is 5.9.
                    3) This company is another video game development company, making AAA games which are likely very big and so this is a higher quality company. 
                    This company has a lot of funding too. The ranking is 6.6.
                    ...
                    10) Mythical Games is a video game engine, not a video game development company. This seems quite irrelevant compared to the prompt. However, 
                    they have a lot of funding, so the ranking is 4.3.

                    Output: Call the function output with parameter [8.3, 5.9, 6.6, ..., 4.3]
                    """
            },
            {
                "role": "user",
                "content": q + "\n" + ';'.join(result)
            }
        ]

        tools = [
            {
                "type": "function",
                "function": {
                "name": "output",
                "description": "Output the result when we have finished ranking",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "rankings": {
                            "type": "array",
                            "items": {
                                "type": "number",
                            },
                            "description": "a list of rankings of companies, in the correct order"
                        }
                    },
                    "required": [
                        "rankings"
                    ]
                }
            }
            }
        ]

        #allow LLM to think about messages up to this stage
        response = client.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )
        response_message = response.choices[0].message

        #check for function calls at this stage
        tool_calls = response_message.tool_calls
        if tool_calls: #if there was a function call
            # for each function call, we run the function
            for tool_call in tool_calls:
                rankings = json.loads(tool_call.function.arguments)["rankings"]

        with open(f"sourcing/results/{test}.txt", "w") as file:
            file.write(q)
            for line in result:
                file.write(line)

            #file.write("Relevance Rankings: ")
            #file.write(','.join(str(x) for x in rankings))

if TESTING:
    #testing rig for determining how accurate ranking results are
    testing()
else:
    query = input("Input a query\n") #Take the initial input query
    controller(query)