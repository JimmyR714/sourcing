from openai import OpenAI
import json
import pycrunchbase


client = OpenAI()
cb = CrunchBase(CRUNCHBASE_API_KEY)

# Function to search crunchbase for results related to a query
# q is a carefully formatted query
# Returns a list of length n containing companies that match the query
def searchCrunchbase(query, n=100):
    pass

# Function to search github for results related to a query
# q is a carefully formatted query
# Returns a list of length n containing companies that match the query
def searchGithub(query, n=100):
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
        available_functions = {
            "searchGithub": searchGithub,
            "searchCrunchbase": searchCrunchbase,
            "getFounder": getFounder,
            "getFunding": getFunding,
            "rank": rank,
            "output": output
        } 
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
        
        

main()