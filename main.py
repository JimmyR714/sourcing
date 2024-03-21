from openai import OpenAI
import json
import requests
import pandas as pd
from operator import itemgetter
import os
from dotenv import load_dotenv
from embeddings_utils import *

load_dotenv()

CB_API_KEY = os.getenv("CB_API_KEY")

MAX_FUNDING = 10000000
client = OpenAI()

# Function to get the embedding for some text. Primarily used for comparing with query
def get_embedding(text, model = "text-embedding-3-small"):
    text = text.replace("\n", " ") #tidy text
    return client.embeddings.create(input = [text], model=model).data[0].embedding

# Function to search crunchbase for results related to a query
# The query can consist of categories 
# Returns a dataframe containing the companies found
# TODO add more parameters to this function to make the search more customisable
def searchCrunchbaseCompanies(categories, n=50):
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
            "operating_status" #TODO founding date after 2021
        ],
        "limit": n, #TODO change this
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
            #{
            #    "type": "predicate",
            #    "field_id": "founded_on",
            #    "operator_id": "gte",
            #    "values": ["2021"] #founding date after 2021
            #}
        ],
        "order": [
            {
                "field_id": "rank_org",
                "sort": "asc"
            }
        ]
    }

    url = "https://api.crunchbase.com/api/v4/searches/organizations?user_key="+CB_API_KEY
    headers = {"accept": "application/json"}

    r = requests.post(url=url, headers=headers, json=queryJSON)
    result = json.loads(r.text) #JSON containing all companies from this query

    #clean the data
    raw = pd.json_normalize(result["entities"])

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
    master["funding"] = raw["properties.funding_total.value_usd"] #TODO fix the bug where funding cannot be collected
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
        return "Name: " + c["identifier.value"] + "; Description: " + c["short_description"] + "; Valuation: " + c["valuation"] + "; Status: " + c["status"]
        #TODO change valuation to funding ideally

    url = f"https://api.crunchbase.com/api/v4/entities/people/{founderUUID}?user_key="+CB_API_KEY
    headers = {"accept": "application/json"}

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
    return f"""Name: {founder["name"]}; Gender: {founder["gender"]}; Born on: {founder["born_on"]}; Located in: {founder["location"]};
    Degrees: {founder["degrees"]}; Previous Jobs: {founder["jobs"]}; Previous Companies: {founder["companies"]}"""

# Function that takes a dataframe of companies, a query, 
# and reduces the dataframe to the n most relevant companies
# Returns the refined dataframe
def refine(df, query, n=100):
    #process table into information that LLM can use to create embedding
    df["pre-embedding"] = (
        "Name: " + df["company"].str.strip() +
        "; Summary: " + df["description"].str.strip() +
        "; Industries: " + df["categories"].str.strip() +
        "; Location: " + df["location"].str.strip() #+
        #"; Employees: " + df["num_of_employees"].str.strip() #more info could be added, but may distract LLM
        #include investor names, founder background (possibly at a later stage)
        )
    df["embedding"] = df["pre-embedding"].apply(lambda x: get_embedding(x, model='text-embedding-3-small'))

    #get the embedding for the query
    query_embedding = get_embedding(query)

    #find relevance of companies
    df["embedding_distance"] = df["embedding"].apply(lambda x: abs(distance_from_embedding(query_embedding, x, distance_metric="cosine")))
    #choose the n most relevant companies
    refined = df.nsmallest(n, "embedding_distance")
    refined.to_csv("embeddings.csv",  sep="\t", encoding="utf-8")
    return refined

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
    #ToT works well here
    #TODO ToT implementation can be much cleaner and more advanced here, this is only very basic to ensure evaluation is decent
    company_info = companies.apply(lambda r: f"""
        Name: {r.company}; Description: {r.description}; Categories: {r.categories}; Employees: {r.num_of_employees}; Revenue: {r.revenue};
        Location: {r.location}; Funding: {str(r.funding.astype(int))}; Funding Stage: {r.funding_stage}; 
        Number of Investors: {r.num_of_investors}; Top Investors: {str(r.investors)}; 
        Weekly Rank Change: {str(r.rank_change_week)}; Monthly Rank Change: {str(r.rank_change_month)}; Quarterly Rank Change: {str(r.rank_change_quarter)};
        Rank: {str(r.rank)}; Founders: {r.founder_backgrounds}
        """).to_string()
    def thought():
        messages = [
            {
                "role": "system", 
                "content": 
                    f"""
                    You are a helpful assistant that takes as input a set of companies. Your job is to 
                    choose the {str(n)} most relevant companies according to the following criteria:
                    1) The company must be relevant to the query
                    2) Companies that have founders that are based in the US are better than those that don't
                    3) Companies that have founders that have degrees from top-tier universities 
                    e.g. Oxford, Cambridge, Harvard, Stanford, MIT, etc are better that those that don't
                    4) Companies that have founders that have previously been employed by top-tier companies 
                    e.g. Google, Amazon, Apple, Meta etc are better than those that don't
                    5) Companies that have founders that have had previous entrepeneurial success
                    e.g. founding a company with a high valuation, founding a company that has been acquired, etc
                    are better than those that don't
                    6) Companies that have a higher improvement over the last quarter, month and week are better
                    7) Companies that have top-tier investors are better than those that don't
                    You should evaulate the companies according to all criteria, with slightly more weight
                    given to the higher criteria e.g. 1,2 than the lower ones.
                    You should output the names of the top {str(n)} companies by descending rank as a list of integers.
                    """
            },
            { #eventually, this will be filled with a CoT ReAct prompt
                "role": "user", 
                "content": 
                    "Q: The query is: " + query + "\nThe companies are:\n" + company_info + """
                    \n Let's think about this step by step, and have a good reason according to the evaluation points for each choice. 
                    We MUST return the numerical indices of our choices made, in a clear list at the end of our response."""
            }
        ]

        response = client.chat.completions.create(model="gpt-4-turbo-preview", messages=messages)
        return response.choices[0].message.content
    
    messages = [
        {
            "role": "system",
            "content":
                """You are a helpful assistant that is able to evaluate a list of companies that relate to a query. 
                You can perform a thought to acquire an evaluation of the companies. You should think at least 5 times.
                After thinking, you will have the evaluations of certain companies, at which stage, you should choose the 10
                that relate most to the query. Output the indices that relate to these 10 companies at the end."""
        },
        {
            "role": "user",
            "content": "Use thought() to perform thoughts. Don't output until you hav completed the thoughts. The query to relate the evaluations to is: " + query + """
            ; The company information should not be evaluated here, but is provided so you can ensure that evaluations are correct. The company
            information is as follows: """ + company_info + "Let's think about this step by step, and have a good reason for each choice."
        }
    ]

    tools = [
        {
            "type": "function",
            "function": {
                "name": "thought",
                "description": "perform an evaluation of the companies. Returns the indices of the chosen companies along with an evaluation."
            }
        }
    ]

    response = client.chat.completions.create(model="gpt-4-turbo-preview", messages=messages, tools=tools, tool_choice="auto",)
    response_message = response.choices[0].message
    tool_calls = response_message.tool_calls
    if tool_calls:
        for tool_call in tool_calls:
            messages.append(
                {
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": "thought",
                "content": thought(),
                }
            )

    messages.append(
        {
            "role": "user",
            "content": 
            """
            Now that you have done the thoughts, you must return the list of the 10 indices of companies that relate most to the query via their evaluations.
            You should include an evaluation with each explaining why they seemed the most relevant to the query, and why you chose them.
            Put the list of indices clearly at the end"""
        }
    )

    response = client.chat.completions.create(model="gpt-4-turbo-preview", messages=messages)
    return response.choices[0].message.content


# Function that takes a list of companies, each with their relevant company information and outputs the necessary information about each one
# Input data contains all information
# Much more could be returned right now
def outputCompanies(companies, indices):
    #assert(len(indices) <= 10)
    def outputCompany(company):
        return company["company"] + "\n" + company["website"] + "\n" + company["description"] + "\n" + company["founder_backgrounds"] + "\n" + str(company["funding"]) + "\n"
    
    print("------------------------------------------------------------\n")
    for rank,index in enumerate(indices):
        print(f"{rank+1}.\n{outputCompany(companies.iloc[index])}\n------------------------------------------------------------\n")

# LLM that controls the flow of the program. Uses a crew of LLMs to decide what tools to use, 
# complete different parts of the procedure, etc
# Always runs in 6 sections:
# 1) Pre-search preparation
# 2) Searching for companies
# 3) Refinement of searches
# 4) Pre-ranking preparation
# 5) Ranking companies
# 6) Outputting companies
def controller():
    query = input("Input a query\n") #Take the initial input query

    #define initial messages. These start off as a CoT ReAct Query
    messages = [
                {"role": "system", 
                 "content": 
                    """
                    You are a helpful assistant that takes an input query which is a description of a company. 
                    Your job is to find the top 10 companies related to this query.
                    You will do this in 6 stages:
                    1) Get all information needed to search the web, e.g. get the crunchbase categories related to the query so we can search crunchbase
                    2) Search the web for 1000s of companies relating to the query, e.g. search crunchbase using the categories we just obtained. You cannot do this at the same time as finding the categories.
                    3) Refine the set of companies down to around 100 using the information found and the query
                    4) Find all information relevant to our final 100 companies, including founder backgrounds
                    5) Rank the top 10 companies using all of the information found and the query
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
                    I have the categories to search for. I want to search for 1000 companies related to these categories.
                    Act 2: searchCrunchbaseCompanies(categories = ["blockchain-investment", "cryptocurrency"], n=1000)
                    Observation 2: 1000 companies found

                    Thought 3: I have 1000 companies, but I need to refine this down to 100.
                    Act 3: refine("blockchain investment companies", n=100)
                    Observation 3: 100 companies remaining.

                    Thought 4: I need to find the more detailed information on each of the 100 remaining companies. I should find the 
                    information about the background of each founder.
                    Act 4: searchCrunchbaseFounders()
                    Observation 4: Founder backgrounds have been located.

                    Thought 5: Now that I have the more in depth information, I need to rank each of the companies to find the top 10. 
                    Act 5: rank("blockchain investment companies", n=10)
                    Observation 5: The top 10 companies are stored at indices [4,1,9,39,12,43,99,64,70,71]

                    Thought 6: I have the top 10 companies, I just need to output them
                    Act 6: outputCompanies([4,1,9,39,12,43,99,64,70,71])
                    Observation 6: Outputting finished. Task complete.

                    Q: Give me the top 10 indie game development companies
                    A:
                    Thought 1: I need to get all information needed to search the web. I will be searching crunchbase to find the companies.
                    To search crunchbase, I need the categories to search for that relate to the query. I should only try to choose a single list
                    of categories, so I should call chooseCategory only once, using the key information from the query.
                    Act 1: chooseCategory("indie game development")
                    Observation 1: I now have the categories - ["gaming", "game-development"]

                    Thought 2: I need to perform a search for companies related to the query. I will be searching crunchbase for this. 
                    I have the categories to search for. I want to search for 1000 companies related to these categories.
                    Act 2: searchCrunchbaseCompanies(categories = ["gaming", "game-development"], n=1000)
                    Observation 2: 1000 companies found. 

                    Thought 3: I have 1000 companies, but I need to refine this down to 100.
                    Act 3: refine("indie game development, n=100")
                    Observation 3: 100 companies remaining.

                    Thought 4: I need to find the more detailed information on each of the 100 remaining companies. I should find the 
                    information about the background of each founder.
                    Act 4: searchCrunchbaseFounders()
                    Observation 4: Founder backgrounds have been located.

                    Thought 5: Now that I have the more in depth information, I need to rank each of the companies to find the top 10. 
                    Act 5: rank("indie game development", n=10)
                    Observation 5: The top 10 companies are stored at indices [61, 21, 34, 5, 72, 87, 20, 29, 71, 2]

                    Thought 6: I have the top 10 companies, I just need to output them
                    Act 6: outputCompanies([61, 21, 34, 5, 72, 87, 20, 29, 71, 2])
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
                            "description": "number of results for search to return"
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
                "description": "rank the top 10 companies based on the found information",
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
                "description": "takes a set of companies and their detailed information, along with a list of indices, and outputs the website URL, name, description, founders and their background, funding and its background for each company at an index in the dataframe",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "indices": {
                            "type": "array",
                            "items": {
                                "type": "number",
                                "description": "an index in the dataframe"
                            },
                            "description": "the list of indices of the companies to be outputted"
                        }
                    },
                    "required": [
                        "indices"
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
            #TODO error handling for invalid JSONs
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
                        #TODO there is a bug where this can be called on stage 1, and it guesses categories
                        local_args.update({"crunchbase_companies": searchCrunchbaseCompanies(function_args["categories"], function_args["n"])})
                        function_response = str(local_args["crunchbase_companies"].shape[0]) + " companies found."

                    case "searchCrunchbaseFounders": 
                        print("Searching for founders on Crunchbase... [CURRENTLY BROKEN]")
                        #TODO most crunchbase founders don't have their degree info on there, so this is currently non-functional
                        local_args["refined_companies"]["founder_backgrounds"] = local_args["refined_companies"]["founder_names"]
                        #f = local_args["refined_companies"]["founder_uuids"]
                        #local_args["refined_companies"]["founder_background"] = f.apply(lambda x: founderBackgrounds(x))
                        function_response = "Founder backgrounds have been located"

                    case "refine":
                        print("Refining Search...")
                        local_args.update({"refined_companies": refine(local_args["crunchbase_companies"], function_args["query"], function_args["n"])})
                        function_response = str(local_args["refined_companies"].shape[0]) + " remaining"

                    case "chooseCategory":
                        print("Choosing categories...")
                        #TODO there is a bug where this can be called twice by LLM, and we lose initial results
                        function_response = str(chooseCategory(function_args["query"]))

                    case "rank":
                        print("Ranking companies...")
                        function_response = rank(local_args["refined_companies"], function_args["query"], function_args["n"])

                    case "outputCompanies":
                        print("Outputting companies...")
                        outputCompanies(local_args["refined_companies"], function_args["indices"])
                        function_response = "Outputting finished. Task complete."

                #add the necessary function response to the messages for the next conversation
                messages.append(
                    {
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": function_response,
                    }
                )  

controller()