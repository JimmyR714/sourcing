from openai import OpenAI
from serpapi import GoogleSearch
import json
SERP_API_KEY = "c1a6aadd8345bc0a544ed5904f624bc74b25ef5f527ff8a46178b469a0a6d038"

client = OpenAI()

# Function to format the initial query to be more appropriate for searching each platform
# Returns a JSON of 

# Function to search a website for results related to a query
# q is a carefully formatted query
# Returns a list of length n containing companies that match the query q
def searchWeb(q, website = "", n=100):
    if website != "": #if there is a specific website that we want to search for
        searchQuery = "site:" + website + q
    else: #if we want to search more generally
        searchQuery = q

    #search the query
    params = {
        "api_key": SERP_API_KEY,
        "engine": "google",
        "q": searchQuery,
        "google_domain": "google.com",
        "hl": "en",
        "num": n
    }

    search = GoogleSearch(params)
    results = search.get_dict()

def getFounder(company):
    pass

def getFunding(company):
    pass

def rank(companies, n=10):
    pass

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

                    Q: Find all AI agent framework and AI agent developer tool startups
                    """
                }
            ]
    
    #define our functions to call
    tools = [
        {
            "type": "function",
            "function": {
                "name": "searchWeb",
                "description": "Search a query on the web on a particular website ",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "query to be searched"
                        },
                        "website": {
                            "type": "string",
                            "description": "website to be searched. leave blank if we want all websites",
                            "enum": [
                                "github.com",
                                "crunchbase.com",
                            ""
                            ]
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
        available_functions = {
            "searchWeb": searchWeb,
            "getFounder": getFounder,
            "getFunding": getFunding,
            "rank": rank,
            "output": output
        } 
        messages.append(response)  #extend conversation with assistant's reply
        # for each function call, we run the function
        for tool_call in tool_calls:
            function_name = tool_call.function.name
            function_to_call = available_functions[function_name]
            function_args = json.loads(tool_call.function.arguments)
            function_response = function_to_call(
                location=function_args.get("location"),
                unit=function_args.get("unit"),
            )
            messages.append(
                {
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": function_name,
                    "content": function_response,
                }
            )  # extend conversation with function response

main()