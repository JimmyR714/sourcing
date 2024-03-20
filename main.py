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
            "operating_status" #TODO founding date after 2021
        ],
        "limit": n,
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
            {
                "type": "predicate",
                "field_id": "founded_on",
                "operator_id": "gte",
                "values": [{"precision": "year", "value": "2021"}] #founding date after 2021
            }
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
    master["company"] = raw["properties.identifier.value"]
    master["description"] = raw["properties.short_description"]
    master["categories"] = raw["properties.categories"].apply(lambda x: list(map(itemgetter('value'), x)if isinstance(x, list) else ["Not found"])).apply(lambda x : ",".join(map(str, x)))
    master["num_of_employees"] = raw["properties.num_employees_enum"].map(employee_range)
    master["revenue"] = raw["properties.revenue_range"].map(revenue_range)
    master["website"] = raw["properties.website_url"]
    master["location"] = raw["properties.location_identifiers"].apply(lambda x: list(map(itemgetter('value'), x)if isinstance(x, list) else ["Not found"])).apply(lambda x : ",".join(map(str, x)))
    master["funding"] = raw["properties.funding_total"] #TODO fix the bug where funding cannot be collected
    master["funding_stage"] = raw["properties.funding_stage"]
    master["founders"] = raw["properties.founder_identifiers"].apply(lambda x: list(map(itemgetter('value'), x)if isinstance(x, list) else ["Not found"])).apply(lambda x : ",".join(map(str, x)))
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

# Function that searches crunchbase for founders/investors given their uuid
# Much more information can be acquired if necessary
# returns a dataframe containing the information about the person
def searchCrunchbaseFounder(founderUUID):
    # a lot more information could be added to each of these functions, but we need to be careful not to do too much or else
    # evaluating the quality will get expensive and detract from what we want LLM to look for
    def getDegree(d):
        return "Type: " + d["type_name"] + "; School: " + d["school_identifier.value"] + "; Subject: " + d["subject"] + "Completed on: " + d["completed_on"]

    def getJob(j):
        return "Title: " + j["title"] + "; Employer: " + j["organization_identifier"] + "; Started: " + j["started_on.value"] + "; Finished: " + j["ended_on.value"]

    def getCompany(c):
        return "Name: " + c["identifier.value"] + "; Description: " + c["short_description"] + "; Valuation: " + c["valuation"] + "; Status: " + c["status"]


    url = f"https://api.crunchbase.com/api/v4/entities/people/{founderUUID}?user_key="+CB_API_KEY
    headers = {"accept": "application/json"}

    r = requests.get(url=url, header=headers)
    result = json.loads(r.text) #JSON containing all information about the founder

    #clean the data
    raw = pd.json_normalize(result)
    founder = pd.DataFrame()
    founder["name"] = raw["properties.identifier.value"]
    founder["gender"] = raw["properties.gender"]
    founder["born_on"] = raw["properties.born_on"]
    founder["degrees"] = raw["cards.degrees"].apply(lambda x: list(map(getDegree, x) if isinstance(x, list) else ["Not found"])).apply(lambda x : ",".join(map(str, x)))
    founder["location"] = raw["properties.location_identifiers"]
    founder["jobs"] = raw["cards.jobs"].apply(lambda x: list(map(getJob, x) if isinstance(x, list) else ["Not found"])).apply(lambda x : ",".join(map(str, x)))
    founder["companies"] = raw["cards.founded_organizations"].apply(lambda x: list(map(getCompany, x) if isinstance(x, list) else ["Not found"])).apply(lambda x : ",".join(map(str, x)))

    return founder

# Function that takes a dataframe for a founder and formats it into a string
def outputFounder(f):
    return f"Name: {f["name"]}; Gender: {f["gender"]}; Born on: {f["born_on"]}; Located in: {f["location"]}\nDegrees: {f["degrees"]}\nPrevious Jobs: {f["jobs"]}\nPrevious Companies: {f["companies"]}"

# Function that takes a dataframe of companies, a query, 
# and reduces the dataframe to the n most relevant companies
# Returns the refined dataframe
def refine(df, n, query):
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
    query_embedding = get_embedding[query]

    #find relevance of companies
    df["embedding_distance"] = df["embedding"].apply(lambda x: abs(distance_from_embedding(query_embedding, x, distance_metric="cosine")))
    #choose the n most relevant companies
    refined = df.nsmallest(n, "embedding_distance")
    return refined

# Function that takes a query and returns crunchbase categories that most relate to that query
# Currently requires category list; may be difficult to adapt to work without the category list
def chooseCategory(query):
    categoryList = [] #this will be filled with the roughly 800 categories
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
                """ + categoryList.toString()
        },
        {
            "role": "user",
            "content": 
                """
                Q: Find me the top 10 IT companies that do conulting.
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
    return response

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
                3) Companies that have founders that have previously been employed by top-tier companies 
                e.g. Google, Amazon, Apple, Meta etc are better than those that don't
                4) Companies that have founders that have had previous entrepeneurial success
                e.g. founding a company with a high valuation, founding a company that has been acquired, etc
                are better than those that don't
                5) Companies that have a higher improvement over the last quarter, month and week are better
                6) Companies that have top-tier investors are better than those that don't
                You should evaulate the companies according to all criteria, with slightly more weight
                given to the higher criteria e.g. 1,2 than the lower ones.
                You should output the names of the top {str(n)} companies by descending rank as a list of integers.
                """
        },
        {
            "role": "user", 
            "content": 
                f"""
                Q: The query is:
                The companies are:
                {companyDetails1}
                A: 
                {companyAnalysis1} 
                Q: The query is:
                The companies are:
                {companyDetails2}
                A:
                {companyAnalysis2}
                Q: The query is: 
                """ + query + "\nThe companies are:\n" + companies
        }
    ]

    response = client.chat.completions.create(model="gpt-4-turbo-preview", messages=messages)
    return response

# Function that takes a list of companies, each with their relevant company information and outputs the necessary information about each one
# Input data contains all information
# Much more could be returned right now
def outputCompanies(companies, indices):
    #assert(len(indices) <= 10)
    def outputCompany(company):
        return f"{company["company"]}\n{company["website"]}\n{company["description"]}\n{company["founder_info"]}\n{company["funding_info"]}\n"
    
    print("------------------------------------------------------------\n")
    for index,rank in enumerate(indices):
        print(f"{rank+1}.\n{outputCompany(companies[index])}\n------------------------------------------------------------\n")

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
                    Your job is to search GitHub, Crunchbase, and the web to find the 1000 most relevant companies to the query. 
                    Then for each company, you will get the founder along with a description of their professional and educational background. 
                    You will also get the level of funding and where it is coming from. 
                    Then, you will use this information to rank the top 10 best companies based on the similarity of the query, 
                    founder based in the US, founder background is from top-tier universities (e.g. Oxford) or top-tier employers (e.g. Google)
                    or prior entrepreneurial success/exit and less than $10M funding. 
                    For each company in the top 10, you will output: the website URL and name; a brief 10-word description of the company; 
                    a concise description of the background of the founders (if found) in 2 sentences with university and employer names, 
                    and prior entrepreneurial exits (if any); and a background of the funding information (if found).
                    """
                },
                {"role": "user", 
                 "content": 
                    """
                    Q: Tell me the top 10 blockchain investment companies 
                    A: 
                    Thought 1: I need to search GitHub to find the top 100 blockchain investment companies 
                    Act 1: searchGitHub({"query": "blockchain investment companies", "n": 1000}) 
                    Observation 1: I now have the top 100 blockchain investment companies on GitHub

                    Thought 2: I need to search Crunchbase to find the top 100 blockchain investment companies 
                    Act 2: searchCrunchbaseCompanies({"categories": "["blockchain", "investment", "blockchain-investment", "bitcoin", "cryptocurrency" ...]"}) 
                    Observation 2: I now have the top 100 blockchain investment companies on crunchbase

                    Thought 3: I need to choose the most relevant companies from my previous searches that relate to the initial query 
                    Act 3: Remove the companies that are least relevant to the prompt, so I only have 50 left 
                    Observation 3: I have the top 50 blockchain investment companies

                    Thought 4: I need to find the funding and founder for each of the top 50 companies 
                    Act 4: getFunding({"company": "company1"}), getFounder({"company": "company1"}), 
                           getFunding("company": "company2"}), getFounder("company": "company2"}), ... 
                           getFunding({"company": "company50"}), getFounder({"company": "company50"}) 
                    Observation 4: I now have all of the information necessary to rank the top 50 companies

                    Thought 5: I need to rank the top 10 companies 
                    Act 5: rank([{"company": "company1"}, ... {"company": "company50"}]) 
                    Observation 5: I now have the top 10 ranked companies for the query

                    Thought 6: I need to output the information for each of the top 10 companies 
                    Act 6: outputCompany({"company": "company1}), ... outputCompany({"company": "company10"}) 
                    Observation 6: I have finished

                    Q: Find me the best indie game development companies 
                    A: 
                    Thought 1: I need to search GitHub to find the top 100 best indie game development companies 
                    Act 1: searchGitHub({"query": "best indie game development companies", "numResults": 100}) 
                    Observation 1: I now have the top 100 best indie game development companies on GitHub

                    Thought 2: I need to search Crunchbase to find the top 100 indie game development companies 
                    Act 2: searchCrunchbaseCompanies({"categories": "["game-development", "gaming", "indie-game", "indie-game-development" ... ]"}) 
                    Observation 2: I now have the top 100 best indie game development companies on crunchbase

                    Thought 3: I need to choose the most relevant companies from my previous searches that relate to the initial query 
                    Act 3: Remove the companies that are least relevant to the prompt, so I only have 50 left 
                    Observation 3: I have the top 50 indie game development companies

                    Thought 4: I need to find the funding and founder for each of the top 50 companies 
                    Act 4: getFunding({"company": "company1"}), getFounder({"company": "company1"}), 
                           getFunding("company": "company2"}), getFounder("company": "company2"}), ... 
                           getFunding({"company": "company50"}), getFounder({"company": "company50"}) 
                    Observation 4: I now have all of the information necessary to rank the top 50 companies

                    Thought 5: I need to rank the top 10 companies 
                    Act 5: rank([{"company": "company1"}, ... {"company": "company50"}]) 
                    Observation 5: I now have the top 10 ranked companies for the query

                    Thought 6: I need to output the information for each of the top 10 companies 
                    Act 6: outputCompany({"company": "company1}), ... outputCompany({"company": "company10"}) 
                    Observation 6: I have finished

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
                            "description": "number of results for search to return. default is 1000"
                        }
                    },
                    "required": [
                        "categories"
                    ]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "searchCrunchbaseFounders",
                "description": "Search for founders backgrounds on crunchbase",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "df": {
                            "type": "object",
                            "description": "the dataframe containing the founders that we will get the backgrounds of"
                        }
                    },
                    "required": [
                        "df"
                    ]
                }
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
                        "df": {
                            "type": "object",
                            "description": "a large list of companies, with all of the relevant information about them. aquired from searching a website for companies"
                        },
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
                        "df",
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
                            "type": "object",
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
                        "companies": {
                            "type": "array",
                            "items": {
                                "type": "object"
                            },
                            "description": "list of dictionaries, each containing information about a company"
                        }
                    },
                    "required": [
                        "companies"
                    ]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "outputCompanies",
                "description": "takes a dataframe of companies and their detailed information, along with a list of indices, and outputs the website URL, name, description, founders and their background, funding and its background for each company at an index in the dataframe",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "companies": {
                            "type": "object",
                            "description": "all of the required detailed information for the companies to be outputed"
                        },
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
                        "companies",
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
                        local_args.update({"crunchbase_companies": searchCrunchbaseCompanies(function_args["categories"], function_args["n"])})
                        function_response = f"{local_args["companies"].length} companies found"
                    case "searchCrunchbaseFounders": #LLM dosn't know the UUIDs, it will tell us which dataframe to find the founders for
                        for row in function_args["df"]:
                            row["founder_background"] = outputFounder(searchCrunchbaseFounder(row["founder"]))
                        function_response = f"Founder backgrounds have been located"
                    case "refine":
                        local_args.update({"refined_companies": refine(function_args["df"], function_args["n"], function_args["query"])})
                        function_response = f"{local_args["refined_companies"].length} remaining"
                    case "chooseCategory":
                        function_response = str(chooseCategory(function_args["query"]))
                    case "rank":
                        function_response = str(rank(function_args["companies"], function_args["query"], function_args["n"]))
                    case "outputCompanies":
                        outputCompanies(function_args["companies"], function_args["indices"])
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
