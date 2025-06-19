import looker_sdk
import vertexai
from vertexai.preview.generative_models import GenerativeModel, GenerationConfig
from looker_sdk import models40 as models, error
import configparser
import json
import urllib.parse
import re

sdk = looker_sdk.init40('looker.ini')

project_id = 'joon-sandbox' # @param {type:"string"}
location = 'global' # @param {type:"string"}

prompt = '''You are a specialized assistant that translates Looker Explore query URL's into natural language questions. By reading the different parameters of the url (like the fields used, filters, etc.) you are able to generate a natural language question.
Please keep these responses short and concise using 1-2 sentences max in your repsonse. Make sure to generate a response that sounds like it's coming from an average person and not a data analyst who is very familiar with the data. Each request will contain an "input" and an "output" field. The "output" field will be the Looker Explore query url. The "input" field will be the natural language question that you will fill in/generate. Here is an example of a properly formatted response:
Example:
{"input": "customer with lifetime revenue > 100", "output": "fields=user_order_facts.lifetime_revenue&f[user_order_facts.lifetime_revenue]=>100&sorts=user_order_facts.lifetime_revenue desc 0&limit=500"}
'''

parameters = {"max_output_tokens": 2500, "temperature": 0.2, "candidate_count": 1}
vertexai.init(project=project_id, location=location)

def generate_input(request):
    model = GenerativeModel("gemini-2.5-flash-lite-preview-06-17")
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


model = 'bkg_spoke' # @param {type:"string"}
explore = 'dms_bkg_cntr_mig' # @param {type:"string"}

data = fetchExploreMetadata(model, explore, 'fields')

with open(f"./{model}::{explore}.txt", "w") as f:
  f.write(formatExploreMetadata(data))


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
              "query.count",
              "history.count"
            ],
            pivots=None,
            fill_fields=None,
            filters={
              "query.view": explore,
              "history.status": "complete",
              # "user.email":""
            },
            filter_expression=None,
            sorts = [],
            # sorts=[
            #   "history.count desc"
            #   "query.view"
            # ],
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



data = fetchQueryUrlMetadata('dms_bkg_cntr_mig')
# categorization =
categorized_queries = explore_url_categorization(data)



url_prompts = []

for key in categorized_queries.keys():
  if type(categorized_queries[key]) == list:
    for url in categorized_queries[key][0:3]:
      url_prompts.append(generate_input(json.dumps({"input": "", "output": url})) + '\n')

  else:
    for key2 in categorized_queries[key].keys():
      for url in categorized_queries[key][key2][0:3]:
        url_prompts.append(generate_input(json.dumps({"input": "", "output": url})) + '\n')


with open("./examples.jsonl", "a") as f:
  f.writelines(url_prompts)