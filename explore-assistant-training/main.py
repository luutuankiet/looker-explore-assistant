# %%
# MIT License

# Copyright (c) 2023 Looker Data Sciences, Inc.

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# %% [markdown]
# # Explore Assistant Examples Generation
# 
# This notebook is a companion to the [Explore Assistant Looker + GenAI Solution](https://github.com/LukaFontanilla/looker-explore-assistant) and will take you through some example code for:
# 
# 
# *   Formatting Looker Explore Metadata for Prompt Stuffing
# *   Generating NLQ to Explore URL examples from your data and Looker Explore usage
# *   Categorizing those examples by different Looker query types
# 
# 

# %% [markdown]
# ## Install Dependencies

# %%
# %pip install looker-sdk
# %pip install --upgrade google-cloud-aiplatform

# %% [markdown]
# ## Import Required Packages

# %%
import looker_sdk
import vertexai
from vertexai.preview.generative_models import GenerativeModel, GenerationConfig
from looker_sdk import models40 as models, error
import configparser
import json
import urllib.parse
import re

# %% [markdown]
# ## Configure Application Default Credentials with GCloud
# 
# This [Exports ADC credentials](https://cloud.google.com/docs/authentication/application-default-credentials) to your environment. ***Make sure to set the quota project to a GCP project that has the Vertex AI API enabled.***

# %%
# !gcloud auth application-default login

# %%
# !gcloud config set project looker-private-demo
# !gcloud auth application-default set-quota-project looker-private-demo

# %% [markdown]
# ## Setup Looker SDK
# 
# Steps for configuring the Looker Python SDK:
# 
# 
# 1.   Create a file named `looker.ini`
# 2.   Using the example below, fill in the variables as they are for your environment. ***You will need Looker API credentials for a user that has at least `explore` level permissions.***
# 2.   Upload that file into your Colab Notebook
# 
# 
# `looker_example.ini`
# ```
# [Looker]
# base_url=
# client_id=
# client_secret=
# verify_ssl=true
# ```
# 
# 
# 
# 

# %%
sdk = looker_sdk.init40('looker.ini')

# %% [markdown]
# ## Setup Vertex Python SDK with Gemini Model
# 
# Please set the following variables prior to running the cell:
# 
# 

# %%
project_id = 'joon-sandbox' # @param {type:"string"}
location = 'asia-southeast1' # @param {type:"string"}

prompt = '''You are a specialized assistant that translates Looker Explore query URL's into natural language questions. By reading the different parameters of the url (like the fields used, filters, etc.) you are able to generate a natural language question.
Please keep these responses short and concise using 1-2 sentences max in your repsonse. Make sure to generate a response that sounds like it's coming from an average person and not a data analyst who is very familiar with the data. Each request will contain an "input" and an "output" field. The "output" field will be the Looker Explore query url. The "input" field will be the natural language question that you will fill in/generate. Here is an example of a properly formatted response:
Output the result in plain raw text without any Markdown formatting or tripple backticks. Strip all tripplebackticks out if you have it in your resp. Do not acknowledge or reply any content else other than the following response. ONLY reply in this format: {"input": value, "output": value}. When unsure, do not reply.
Example:
{"input": "total billable hours by engineer", "output": "fields=fct__jira__worklogs.total_billable_hours,worklog_creator.name&f[fct__jira__worklogs.started_date_filter]=this+quarter&f[fct__jira__worklogs.date_granularity]=month&f[fct__jira__worklogs.date]=-NULL&f[worklog_creator.is_active]=Yes&sorts=fct__jira__worklogs.total_billable_hours desc 0&limit=5000"}
'''
# prompt = '''You are a specialized assistant that translates Looker Explore query URL's into natural language questions. By reading the different parameters of the url (like the fields used, filters, etc.) you are able to generate a natural language question.
# Please keep these responses short and concise using 1-2 sentences max in your repsonse. Make sure to generate a response that sounds like it's coming from an average person and not a data analyst who is very familiar with the data. Each request will contain an "input" and an "output" field. The "output" field will be the Looker Explore query url. The "input" field will be the natural language question that you will fill in/generate. Here is an example of a properly formatted response:
# Example:
# {"input": "customer with lifetime revenue > 100", "output": "fields=user_order_facts.lifetime_revenue&f[user_order_facts.lifetime_revenue]=>100&sorts=user_order_facts.lifetime_revenue desc 0&limit=500"}
# '''

parameters = {"max_output_tokens": 2500, "temperature": 0.2, "candidate_count": 1}
vertexai.init(project=project_id, location=location)

def generate_input(request):
    model = GenerativeModel("gemini-pro")
    # make prediction to generate Looker Explore URL
    response =  model.generate_content(
        contents=prompt + request,
        generation_config=GenerationConfig(
            temperature=0.2,
            top_p=0.8,
            top_k=40,
            max_output_tokens=1000,
            candidate_count=1
        )
    )

    return response.text

# %% [markdown]
# ## Format Looker Explore Metadata for Prompt Stuffing
# 
# The next two cells provide the Looker Explore Metadata the LLM needs to be able to generate Looker Explore URL's from natural language. This is all done through Prompt Stuffing.
# 
# 
# *   Fetches all the field metadata from the LookML model for a given Explore
# *   Generates two arrays containing all the measures and dimensions with the name, type, description and any other relevant attribute you'd like to include
# *   Formats that into a structured text variable and writes it to a txt file in the format of `model::explore.txt`
# 
# 
# 
# 

# %%
def fetchExploreMetadata(model,explore,fields):
  data = sdk.lookml_model_explore(model,explore,fields)

  # Dimensions
  dimensions = []
  for field in data.fields.dimensions:
    dimensions.append(f"name: {field.name}, type: {field.type}, description: {field.description} \n")

  # # Measures
  measures = []
  for field in data.fields.measures:
    measures.append(f"name: {field.name}, type: {field.type}, description: {field.description} \n")

  return {
      "dimensions": dimensions,
      "measures": measures
  }


def formatExploreMetadata(data):
  return f"""
  Dimensions Used to group by information:\n {''.join(data['dimensions'])}
  Measures are used to perform calculations/aggregations (if top, bottom, total, sum, etc. are used include a measure):\n {''.join(data['measures'])}
  """


# %%
model = 'fivetran_joon_4_joon' # @param {type:"string"}
explore = 'fct__jira__worklogs' # @param {type:"string"}

data = fetchExploreMetadata(model, explore, 'fields')

with open(f"./{model}::{explore}.txt", "w") as f:
  f.write(formatExploreMetadata(data))

# %% [markdown]
# ## Setup Explore URL Parser & Categorizer
# 
# The following cells setup the functions used to generate commmon and representative Looker Explore query URL's that are labeled via Gen AI for the LLM to use in it's reasoning.
# 
# *   CONSTANTS: Regex patterns for Looker Query filter string parsing
# *   LOOKER QUERY METHODS: The functions for fetching historical queries and parsing their metadata for an expanded URL
# *   LOOKER URL PARSER FUNCTIONS: Functions used to parse and categorize example URL's into specific categories of queries
# 
# 
# 
# 

# %%
### CONSTANTS

# Time / Date Regex Patterns
time_relative_pattern = r"(\d+)\s+(month|week|day|year)?(?:\s+ago)?"
time_range_pattern = r"\b(\d+)\s+(month|week|day|year)s?\s+ago\s+for\s+\1\s+\2\b"

# Numerical Patterns
numerical_comparison_pattern = r"^(>|>=|<|<=|<>)?(\d+)$"
numerical_range_pattern = r"\b(>|>=|<|<=|<>)?(\d+)?\s+(AND|OR)?\s+(>|>=|<|<=|<>)?(\d+)"

# String Patterns
string_catch_all_pattern = r"\w"
string_multiple_pattern = r"\w,+\w"
categorized_queries = {}
categorized_queries_filters = {}

### END


### LOOKER QUERY METHODS


def fetchQueryUrlMetadata(explore: str):
  try:
    response = sdk.run_inline_query(
        result_format='json',
        cache=True,
        body=models.WriteQuery(
            model="system__activity",
            view="history",
            fields=[
              "query.slug",
              "query.view",
              "query.dynamic_fields",
              "query.formatted_fields",
              "query.filters",
              "query.filter_expression",
              "query.formatted_pivots",
              "query.sorts",
              "query.limit",
              "query.column_limit",
              "query.count"
            ],
            pivots=None,
            fill_fields=None,
            filters={
              "query.view": explore,
              "history.status": "complete",
              # "user.email":""
            },
            filter_expression=None,
            sorts=[
              "history.completed_time desc"
              "query.view"
            ],
            limit="10",
        )
    )

    return json.loads(response)[0:10]
  except error.SDKError as e:
    print(e.message)



def fetchQueryUrl(slug: str):
  query_url = sdk.query_for_slug(slug=slug)
  return query_url

### END


### LOOKER URL PARSER FUNCTIONS

# limit categorization
def limit_categorization(query,url):
  if "query.limit" in query and query['query.limit'] != None:
      categorized_queries.setdefault('limit',[])
      categorized_queries['limit'].append(url)

# dynamic fields categorization
def dynamic_fields_categorization(query,url):
  if "query.dynamic_fields" in query and query['query.dynamic_fields'] != None:
      categorized_queries.setdefault('dynamic_fields',[])
      categorized_queries['dynamic_fields'].append(url)

# sorts categorization
def sorts_categorization(query,url):
  if "query.sorts" in query and query['query.sorts'] != None:
      categorized_queries.setdefault('sorts',[])
      categorized_queries['sorts'].append(url)

# filter expression categorization
def filter_expression_categorization(query,url):
  if "query.filter_expression" in query and query['query.filter_expression'] != None:
      categorized_queries.setdefault('filter_expression',[])
      categorized_queries['filter_expression'].append(url)

# pivots categorization
def pivots_categorization(query,url):
  if "query.formatted_pivots" in query and query['query.formatted_pivots'] != None:
      categorized_queries.setdefault('pivots',[])
      categorized_queries['pivots'].append(url)

# filters categorization
def filters_categorization(query,url):
  parsed_filters = json.loads(query['query.filters'])
  keys_copy = tuple(parsed_filters.keys())
  for key in keys_copy:
    if parsed_filters[key] != "":
      if re.findall(time_range_pattern, parsed_filters[key]):
        categorized_queries_filters.setdefault('time_range',[])
        categorized_queries_filters['time_range'].append(url)
        continue
      if re.findall(time_relative_pattern, parsed_filters[key]):
        categorized_queries_filters.setdefault('time_relative',[])
        categorized_queries_filters['time_relative'].append(url)
        continue
      elif re.findall(numerical_comparison_pattern, parsed_filters[key]):
        categorized_queries_filters.setdefault('numerical_comparison',[])
        categorized_queries_filters['numerical_comparison'].append(url)
        continue
      elif re.findall(numerical_range_pattern, parsed_filters[key]):
        categorized_queries_filters.setdefault('numerical_range',[])
        categorized_queries_filters['numerical_range'].append(url)
        continue
      elif re.findall(string_multiple_pattern, parsed_filters[key]):
        categorized_queries_filters.setdefault('string_multiple',[])
        categorized_queries_filters['string_multiple'].append(url)
        continue
      elif re.findall(r"\w",parsed_filters[key]):
        categorized_queries_filters.setdefault('string_standard',[])
        categorized_queries_filters['string_standard'].append(url)
        continue

### END

def explore_url_categorization(data):
  for query in data:
    query_data = fetchQueryUrl(str(query['query.slug']))
    decoded_url = urllib.parse.unquote(query_data.url)

    # return url parameters as a string
    url_parameters = decoded_url.split("?",1)[1].replace("+", " ")
    # remove timezone parameter
    decoded_url_notimezone = re.sub(r"&query_timezone=(.)*&", "&", url_parameters,count=1)
    # remove filter config parameter
    decoded_url_nofilterconfig = re.sub(r"&filter_config=(.)*(?=&|$)", "&", decoded_url_notimezone)[0:-1] if re.sub(r"&filter_config=(.)*(?=&|$)", "&", decoded_url_notimezone)[-1] == "&" else re.sub(r"&filter_config=(.)*(?=&|$)", "&", decoded_url_notimezone)
    # parse vis config parameter only maintain vis type
    vis_config = re.search(r"(&vis=(.)*(?=&|$))", decoded_url_nofilterconfig)

    decoded_url_modifiedvisjson = ''
    if vis_config:
      vis_json_str = vis_config.group(1)
      # regex to search for the vis type (ie. "type":"looker_bar")
      vis_type = re.search(r'("type":\s*"([^,}]+))', vis_json_str)
      # replace the vis config in original url parameter string with the modified vis type
      decoded_url_modifiedvisjson = re.sub(r"(&vis=(.)*(?=&|$))","&vis={" + (vis_type.group(1) if vis_type else '') + "}",decoded_url_nofilterconfig)
    else:
      decoded_url_modifiedvisjson = decoded_url_nofilterconfig

    # run categorization functions to construct object with categorized urls
    limit_categorization(query,decoded_url_modifiedvisjson)
    dynamic_fields_categorization(query,decoded_url_modifiedvisjson)
    sorts_categorization(query,decoded_url_modifiedvisjson)
    filter_expression_categorization(query,decoded_url_modifiedvisjson)
    pivots_categorization(query,decoded_url_modifiedvisjson)
    filters_categorization(query,decoded_url_modifiedvisjson)

  categorized_queries.setdefault('filters',{})
  categorized_queries['filters'] = categorized_queries_filters
  return categorized_queries


# %%
data = fetchQueryUrlMetadata('fct__jira__worklogs')
# data = fetchQueryUrlMetadata('order_items')
# categorization =
categorized_queries = explore_url_categorization(data)

# %%
url_prompts = []

for key in categorized_queries.keys():
  if type(categorized_queries[key]) == list:
    for url in categorized_queries[key][0:3]:
      print(f"generating prompts for {url}\n\n")
      url_prompts.append(generate_input(json.dumps({"input": "", "output": url})) + '\n')

  else:
    for key2 in categorized_queries[key].keys():
      for url in categorized_queries[key][key2][0:3]:
        print(f"generating prompts for {url}\n\n")
        url_prompts.append(generate_input(json.dumps({"input": "", "output": url})) + '\n')

url_prompts = [
    url.replace('```json', '').replace('```', '').strip()
    for url in url_prompts
    if url.strip() != ''
]

with open("./examples.json", "a") as f:
  url_prompts = [json.loads(url_json) for url_json in url_prompts]  
  json.dump(url_prompts,f,indent=2)


