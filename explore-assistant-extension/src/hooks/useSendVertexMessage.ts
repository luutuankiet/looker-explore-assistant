import { ExtensionContext } from '@looker/extension-sdk-react'
import { useCallback, useContext } from 'react'
import { useSelector, useDispatch } from 'react-redux'
import { UtilsHelper } from '../utils/Helper'
import CryptoJS from 'crypto-js'
import { RootState } from '../store'
import process from 'process'
import { useErrorBoundary } from 'react-error-boundary'
import { AssistantState } from '../slices/assistantSlice'
import { isTokenExpired } from '../components/Auth/AuthProvider'
import useSendMessageId from './useSendMessageId'

const unquoteResponse = (response: string | null | undefined) => {
  if(!response) {
    return ''
  }
  return response
    .substring(response.indexOf('fields='))
    .replace(/^`+|`+$/g, '')
    .trim()
}

const parseJSONResponse = (response: string | null | undefined, key: string) => {
// patch for calls coming from the new BE in this format  : 
// '{"message":"Query generated successfully","data":{"response":"Count of Users by first purchase date"}}'
  if (!response || response === '') {
    return ''
  }
  return JSON.parse(response).data[key]
}

export interface ModelParameters {
  max_output_tokens?: number
}

const generateSQL = (
  model_id: string,
  prompt: string,
  parameters: ModelParameters,
) => {
  const escapedPrompt = UtilsHelper.escapeQueryAll(prompt)
  const subselect = `SELECT '` + escapedPrompt + `' AS prompt`

  return `

    SELECT ml_generate_text_llm_result AS generated_content
    FROM
    ML.GENERATE_TEXT(
        MODEL \`${model_id}\`,
        (
          ${subselect}
        ),
        STRUCT(
        0.05 AS temperature,
        1024 AS max_output_tokens,
        0.98 AS top_p,
        TRUE AS flatten_json_output,
        1 AS top_k)
      )

      `
}

function formatContent(field: {
  name?: string
  type?: string
  label?: string
  description?: string
  tags?: string[]
}) {
  let result = ''
  if (field.name) result += 'name: ' + field.name
  if (field.type) result += (result ? ', ' : '') + 'type: ' + field.type
  if (field.label) result += (result ? ', ' : '') + 'label: ' + field.label
  if (field.description)
    result += (result ? ', ' : '') + 'description: ' + field.description
  if (field.tags && field.tags.length)
    result += (result ? ', ' : '') + 'tags: ' + field.tags.join(', ')

  return result
}

const useSendVertexMessage = () => {
  const { showBoundary } = useErrorBoundary()
  // cloud function
  const VERTEX_AI_ENDPOINT = process.env.VERTEX_AI_ENDPOINT || ''


  // bigquery
  const VERTEX_BIGQUERY_LOOKER_CONNECTION_NAME =
    process.env.VERTEX_BIGQUERY_LOOKER_CONNECTION_NAME || ''
  const VERTEX_BIGQUERY_MODEL_ID = process.env.VERTEX_BIGQUERY_MODEL_ID || ''

  const { core40SDK } = useContext(ExtensionContext)
  const { settings, examples, currentExplore, currentExploreThread, userId, me} =
    useSelector((state: RootState) => state.assistant as AssistantState)

  const { access_token } = useSelector((state: RootState) => state.auth)

  const currentExploreKey = currentExplore.exploreKey
  const exploreRefinementExamples = examples.exploreRefinementExamples[currentExploreKey]
  const { getMessageId } = useSendMessageId();

  const vertextBigQuery = async (
    contents: string,
    parameters: ModelParameters,
  ) => {
    const createSQLQuery = await core40SDK.ok(
      core40SDK.create_sql_query({
        connection_name: VERTEX_BIGQUERY_LOOKER_CONNECTION_NAME,
        sql: generateSQL(VERTEX_BIGQUERY_MODEL_ID, contents, parameters),
      }),
    )

    if (createSQLQuery.slug) {
      const runSQLQuery = await core40SDK.ok(
        core40SDK.run_sql_query(createSQLQuery.slug, 'json'),
      )
      const exploreData = await runSQLQuery[0]['generated_content']

      // clean up the data by removing backticks
      const cleanExploreData = exploreData
        .replace(/```json/g, '')
        .replace(/```/g, '')
        .trim()

      return cleanExploreData
    }
  }

  const vertextCloudFunction = useCallback (
    async (
    contents: string,
    raw_prompt: string,
    prompt_type: string,
    parameters: ModelParameters,
  ) => {
    console.log('Within vertextCloudFunction:')
    console.log(currentExploreThread)
    const currentThreadID = currentExploreThread?.uuid
    const currentExploreKey = currentExploreThread?.exploreKey
    console.log(currentThreadID)
      console.log(currentExploreKey)
      

    const messageId = await getMessageId(contents, prompt_type, raw_prompt, parameters, "system");

    const body = JSON.stringify({
      message_id: messageId,
      user_id: me.id,
      thread_id: currentThreadID,
      contents: contents,
      prompt_type: prompt_type,
      raw_prompt: raw_prompt,
      parameters: parameters,
      actor: "system"
    })


  console.log('Making request to Vertex AI:')
  console.log('Endpoint:', VERTEX_AI_ENDPOINT)
  // console.log('Headers:', {
  //   'Content-Type': 'application/json',
  //   'Authorization': `Bearer ${access_token}`
  // })
  console.log('Body:', JSON.parse(body))

    const responseData = await fetch(`${VERTEX_AI_ENDPOINT}/message`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${access_token}`
      },

      body: body,
    })
    if (!responseData.ok) {
      const error = await responseData.text()
      throw new Error(`Server responded with ${responseData.status}: ${error}`)
    }
  
    const responseString = await responseData.text()
    const response = parseJSONResponse(responseString, 'response')
    // const response = await responseData.text()
    return response.trim()

    }, [currentExploreThread]
  )

  // this function is the entrypoint whenever user sends a chat. 
  // the result summarized prompt from vertex will be passed onto next 2 functions :
  // 1. isSummarizationPrompt for categorization.
  // 2. generateExploreUrl to generate looker url
  const summarizePrompts = useCallback(
    async (promptList: string[]) => {
      const contents = `

      Primer
      ----------
      A user is iteractively asking questions to generate an explore URL in Looker. The user is refining his questions by adding more context. The additional prompts he is adding could have conflicting or duplicative information: in those cases, prefer the most recent prompt.

      Here are some example prompts the user has asked so far and how to summarize them:

${exploreRefinementExamples && exploreRefinementExamples
  .map((item) => {
    const inputText = '"' + item.input.join('", "') + '"'
    return `- The sequence of prompts from the user: ${inputText}. The summarized prompts: "${item.output}"`
  })
  .join('\n')}

      Conversation so far
      ----------
      input: ${promptList.map((prompt) => '"' + prompt + '"').join('\n')}

      Task
      ----------
      Summarize the prompts above to generate a single prompt that includes all the relevant information. If there are conflicting or duplicative information, prefer the most recent prompt.

      Only return the summary of the prompt with no extra explanatation or text

    `
      const lastPrompt = promptList[promptList.length - 1];
      const response = await sendMessage(contents, lastPrompt, 'summarizePrompts',{})

      return response
    },
    [exploreRefinementExamples, currentExploreThread],
  )

  const isSummarizationPrompt = async (prompt: string) => {
    const contents = `
      Primer
      ----------

      A user is interacting with an agent that is translating questions to a structured URL query based on the following dictionary. The user is refining his questions by adding more context. You are a very smart observer that will look at one such question and determine whether the user is asking for a data summary, or whether they are continuing to refine their question.

      Task
      ----------
      Determine if the user is asking for a data summary or continuing to refine their question. If they are asking for a summary, they might say things like:

      - summarize the data
      - give me the data
      - data summary
      - tell me more about it
      - explain to me what's going on

      The user said:

      ${prompt}

      Output
      ----------
      Return "data summary" if the user is asking for a data summary, and "refining question" if the user is continuing to refine their question. Only output one answer, no more. Only return one those two options. If you're not sure, return "refining question".

    `
    const response = await sendMessage(contents, prompt, 'isSummarizationPrompt', {})
    return response === 'data summary'
  }

  // this function takes the url generate from generateExploreUrl, execute it to get the data.
  // afterwards the result data is appended to another prompt to vertex requesting to analyze and summarize the data.
  const summarizeExplore = useCallback(
    async (exploreQueryArgs: string) => {
      const params = new URLSearchParams(exploreQueryArgs)

      // Initialize an object to construct the query
      const queryParams: {
        fields: string[]
        filters: Record<string, string>
        sorts: string[]
        limit: string
      } = {
        fields: [],
        filters: {},
        sorts: [],
        limit: '',
      }

      // Iterate over the parameters to fill the query object
      params.forEach((value, key) => {
        if (key === 'fields') {
          queryParams.fields = value.split(',')
        } else if (key.startsWith('f[')) {
          const filterKey = key.match(/\[(.*?)\]/)?.[1]
          if (filterKey) {
            queryParams.filters[filterKey] = value
          }
        } else if (key === 'sorts') {
          queryParams.sorts = value.split(',')
        } else if (key === 'limit') {
          queryParams.limit = value
        }
      })

      // console.log(params)

      // get the contents of the explore query
      const createQuery = await core40SDK.ok(
        core40SDK.create_query({
          model: currentExplore.modelName,
          view: currentExplore.exploreId,

          fields: queryParams.fields || [],
          filters: queryParams.filters || {},
          sorts: queryParams.sorts || [],
          limit: queryParams.limit || '1000',
        }),
      )

      const queryId = createQuery.id
      if (queryId === undefined || queryId === null) {
        return 'There was an error!!'
      }
      const result = await core40SDK.ok(
        core40SDK.run_query({
          query_id: queryId,
          result_format: 'md',
        }),
      )

      if (result.length === 0) {
        return 'There was an error!!'
      }

      const contents = `
      Data
      ----------

      ${result}

      Task
      ----------
      Summarize the data above

    `
      const response = await sendMessage(contents, result, 'summarizeExplore', {})

      const refinedContents = `
      The following text represents summaries of a given dashboard's data.
        Summaries: ${response}

        Make this much more concise for a slide presentation using the following format. The summary should be a markdown documents that contains a list of sections, each section should have the following details:  a section title, which is the title for the given part of the summary, and key points which a list of key points for the concise summary. Data should be returned in each section, you will be penalized if it doesn't adhere to this format. Each summary should only be included once. Do not include the same summary twice.
        `

      const refinedResponse = await sendMessage(refinedContents,response,'summarizeExplore', {})
      return refinedResponse
    },
    [currentExplore],
  )

  const generateExploreUrl = useCallback(
    async (
      prompt: string,
      dimensions: any[],
      measures: any[],
      exploreGenerationExamples: any[],
    ) => {
      try {
        console.log('Within generateExploreUrl:', currentExploreThread)
        const contents = `
            Context
            ----------

            You are a developer who would transalate questions to a structured Looker URL query based on the following instructions.

            Instructions:
              - choose only the fields in the below lookml metadata
              - prioritize the field description, label, tags, and name for what field(s) to use for a given description
              - generate only one answer, no more.
              - use the Examples (at the bottom) for guidance on how to structure the Looker url query
              - try to avoid adding dynamic_fields, provide them when very similar example is found in the bottom
              - never respond with sql, always return an looker explore url as a single string
              - response should start with fields= , as in the Examples section at the bottom

            LookML Metadata
            ----------

            Dimensions Used to group by information (follow the instructions in tags when using a specific field; if map used include a location or lat long dimension;):

          ${dimensions.map(formatContent).join('\n')}

            Measures are used to perform calculations (if top, bottom, total, sum, etc. are used include a measure):

          ${measures.map(formatContent).join('\n')}

            Example
            ----------

          ${exploreGenerationExamples && exploreGenerationExamples
            .map((item) => `input: "${item.input}" ; output: ${item.output}`)
            .join('\n')}

            Input
            ----------
            ${prompt}

            Output
            ----------
        `
        const parameters = {
          max_output_tokens: 1000,
        }
        // console.log(contents)
        const response = await sendMessage(contents, prompt, 'generateExploreUrl',parameters)

        const cleanResponse = unquoteResponse(response)
        // console.log(cleanResponse)

        let toggleString = '&toggle=dat,pik,vis'
        if (settings['show_explore_data'].value) {
          toggleString = '&toggle=pik,vis'
        }

        const newExploreUrl = cleanResponse + toggleString

        return newExploreUrl
      } catch (error) {
        console.error(
          'Error waiting for data (lookml fields & training examples) to load:',
          error,
        )
        showBoundary({
          message:
            'Error waiting for data (lookml fields & training examples) to load:',
          error,
        })
        return
      }
    },
    [settings, currentExploreThread]
  )

  const sendMessage = async (message: string, raw_prompt: string = '', prompt_type: string = '', parameters: ModelParameters) => {
    try {

      let response = ''
      if (VERTEX_AI_ENDPOINT) {
        response = await vertextCloudFunction(message, raw_prompt, prompt_type, parameters)
      }

      if (VERTEX_BIGQUERY_LOOKER_CONNECTION_NAME && VERTEX_BIGQUERY_MODEL_ID) {
        response = await vertextBigQuery(message, parameters)
      }

      return response
    } catch (error) {
      showBoundary(error)
      return
    }
  }

  return {
    generateExploreUrl,
    sendMessage,
    summarizePrompts,
    isSummarizationPrompt,
    summarizeExplore,
  }
}

export default useSendVertexMessage
