from openai import OpenAI
import json
import requests
import pandas as pd
from operator import itemgetter

MAX_FUNDING = 10000000
client = OpenAI()

# Function to search crunchbase for results related to a query
# The query can consist of categories 
# Returns a dataframe containing the companies found
def searchCrunchbase(categories, n=1000):
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
            "location",
            "operating_status"
        ],
        "limit": n,
        "query": [
            {
                "type": "predicate",
                "field_id": "categories",
                "operator_id": "includes",
                "values": categories
            },
            {
                "type": "predicate",
                "field_id": "facet_id",
                "operator_id": "includes",
                "values": ["company"]
            },
            {
                "type": "predicate",
                "field_id": "funding_total",
                "operator_id": "lt",
                "values": [MAX_FUNDING]
            },
            {
                "type": "predicate",
                "field_id": "operating_status",
                "operator_id": "eq",
                "values": ["active"]
            }
        ],
        "order": [
            {
                "field_id": "rank_org",
                "sort": "asc"
            }
        ]
    }

    r = requests.post("https://api.crunchbase.com/api/v4/searches/organizations", params = CB_API_KEY, json = queryJSON)
    result = json.loads(r.text) #JSON containing all companies from this query

    #clean the data
    raw = result["entities"]

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
    master["funding"] = raw["properties.funding_total"]
    master["funding_stage"] = raw["properties.funding_stage"]
    master["founders"] = raw["properties.founder_identifiers"]
    master["investors"] = raw["properties.investor_identifiers"]
    master["num_of_investors"] = raw["properties.num_investors"]
    master["rank_change_week"] = raw["properties.rank_delta_d7"]
    master["rank_change_month"] = raw["properties.rank_delta_d30"]
    master["rank_change_quarter"] = raw["properties.rank_delta_d90"]
    master["rank"] = raw["properties.rank_org"]
    master["status"] = raw["properties.operating_status"]
    master=master.fillna("NA")

    print(master.to_string())








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

# Function to return the founder of a company
def getFounder(company):
    pass

# Function to return the founder of a company
def getFunding(company):
    pass

# Function that ranks the top n companies out of a larger set
def rank(companies, n=10):
    pass

# Function that takes company and gathers then outputs the information about it
def output(company):
    pass

# Main function that executes everything in order according to the flowchart
# Prints the output at the end
def main():
    query = input("Input a query") #Take the initial input query

    #define our CoT ReAct Query
    messages = [
                {"role": "system", 
                 "content": 
                    """
                    You are a helpful assistant that takes an input query which is a description of a company. 
                    Your job is to search GitHub, Crunchbase, and the web to find the 100 most relevant companies to the query. 
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
                    Act 1: searchWeb({"query": "blockchain investment companies", "website": "github.com", "numResults": 100}) 
                    Observation 1: I now have the top 100 blockchain investment companies on GitHub

                    Thought 2: I need to search Crunchbase to find the top 100 blockchain investment companies 
                    Act 2: searchWeb({"query": "blockchain investment companies", "website": "crunchbase.com", "numResults": 100}) 
                    Observation 2: I now have the top 100 blockchain investment companies on crunchbase

                    Thought 3: I need to search the web to find the top 100 blockchain investment companies 
                    Act 3: searchWeb({"query": "blockchain investment companies", "website": "", "numResults": 100}) 
                    Observation 3: I now have the top 100 blockchain investment companies on the web

                    Thought 4: I need to choose the most relevant companies from my previous searches that relate to the initial query 
                    Act 4: Remove the companies that are least relevant to the prompt, so I only have 50 left 
                    Observation 4: I have the top 50 blockchain investment companies

                    Thought 5: I need to find the funding and founder for each of the top 50 companies 
                    Act 5: getFunding({"company": "company1"}), getFounder({"company": "company1"}), 
                           getFunding("company": "company2"}), getFounder("company": "company2"}), ... 
                           getFunding({"company": "company50"}), getFounder({"company": "company50"}) 
                    Observation 5: I now have all of the information necessary to rank the top 50 companies

                    Thought 6: I need to rank the top 10 companies 
                    Act 6: rank([{"company": "company1"}, ... {"company": "company50"}]) 
                    Observation 6: I now have the top 10 ranked companies for the query

                    Thought 7: I need to output the information for each of the top 10 companies 
                    Act 7: outputCompany({"company": "company1}), ... outputCompany({"company": "company10"}) 
                    Observation 7: I have finished

                    Q: Find me the best indie game development companies 
                    A: 
                    Thought 1: I need to search GitHub to find the top 100 best indie game development companies 
                    Act 1: searchWeb({"query": "best indie game development companies", "website": "github.com", "numResults": 100}) 
                    Observation 1: I now have the top 100 best indie game development companies on GitHub

                    Thought 2: I need to search Crunchbase to find the top 100 indie game development companies 
                    Act 2: searchWeb({"query": "indie game development companies", "website": "crunchbase.com", "numResults": 100}) 
                    Observation 2: I now have the top 100 best indie game development companies on crunchbase

                    Thought 3: I need to search the web to find the top 100 best indie game development companies 
                    Act 3: searchWeb({"query": "best indie game development companies", "website": "", "numResults": 100}) 
                    Observation 3: I now have the top 100 best indie game development companies on the web

                    Thought 4: I need to choose the most relevant companies from my previous searches that relate to the initial query 
                    Act 4: Remove the companies that are least relevant to the prompt, so I only have 50 left 
                    Observation 4: I have the top 50 indie game development companies

                    Thought 5: I need to find the funding and founder for each of the top 50 companies 
                    Act 5: getFunding({"company": "company1"}), getFounder({"company": "company1"}), 
                           getFunding("company": "company2"}), getFounder("company": "company2"}), ... 
                           getFunding({"company": "company50"}), getFounder({"company": "company50"}) 
                    Observation 5: I now have all of the information necessary to rank the top 50 companies

                    Thought 6: I need to rank the top 10 companies 
                    Act 6: rank([{"company": "company1"}, ... {"company": "company50"}]) 
                    Observation 6: I now have the top 10 ranked companies for the query

                    Thought 7: I need to output the information for each of the top 10 companies 
                    Act 7: outputCompany({"company": "company1}), ... outputCompany({"company": "company10"}) 
                    Observation 7: I have finished

                    Q: 
                    """ + query
                }
            ]
    
    #define our functions to call
    tools = [
        {
            "type": "function",
            "function": {
                "name": "searchGithub",
                "description": "Search a query on github",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "query to be searched"
                        },
                        "numResults": {
                            "type": "number",
                            "description": "number of results for search to return. default is 100"
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
                "name": "searchCrunchbase",
                "description": "Search a query on crunchbase",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "query to be searched"
                        },
                        "numResults": {
                            "type": "number",
                            "description": "number of results for search to return. default is 100"
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
                "name": "getFunding",
                "description": "find the funding amount and background for a given company",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "company": {
                            "type": "string",
                            "description": "the company that we want to find the funding for"
                        }
                    },
                    "required": [
                        "company"
                    ]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "getFounder",
                "description": "find the founders and their background for a given company",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "company": {
                            "type": "string",
                            "description": "the company that we want to find the founder for"
                        }
                    },
                    "required": [
                        "company"
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
                "name": "outputCompany",
                "description": "takes a company and the detailed information, and outputs the website URL, name, description, founders and their background, funding and its background",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "company": {
                            "type": "object",
                            "description": "all of the required detailed information for the company to be outputted"
                        }
                    },
                    "required": [
                        "company"
                    ]
                }
            }
        }   
    ]

    response = client.chat.completions.create(
        model="gpt-4-turbo-preview",
        messages=messages,
        tools=tools,
        tool_choice="auto",
    )

    #check for function calls
    tool_calls = response.tool_calls
    if tool_calls:
        #TODO error handling for invalid JSONs
        messages.append(response)  #extend conversation with assistant's reply

        # for each function call, we run the function
        for tool_call in tool_calls:
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)

            match function_name:
                case "searchGithub":
                    function_response = searchGithub(
                        query = function_args.get("query"),
                        n = function_args.get("n")
                    )
                case "searchCrunchbase":
                    function_response = searchCrunchbase(
                        query = function_args.get("query"),
                        n = function_args.get("n")
                    )
                case "getFounder":
                    function_response = getFounder(
                        company = function_args.get("company")
                    )
                case "getFunding":
                    function_response = getFounder(
                        company = function_args.get("company")
                    )
                case "rank":
                    function_response = searchGithub(
                        companies = function_args.get("companies"),
                        n = function_args.get("n")
                    )
                case "output":
                    function_response = output(
                        company = function_args.get("company")
                    )

            messages.append(
                {
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": function_name,
                    "content": function_response,
                }
            )  
        


#main()
searchCrunchbase(["AI Agent framework", "AI agent developer tool", "AI"])