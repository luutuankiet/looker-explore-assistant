import { useContext, useEffect, useRef } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import {
  setExploreGenerationExamples,
  setExploreRefinementExamples,
  setExploreSamples,
  setFeedbackCategories,
  ExploreSamples,
  setisBigQueryMetadataLoaded,
  setCurrenExplore,
  RefinementExamples,
  ExploreExamples,
  AssistantState,
  FeedbackCategory
} from '../slices/assistantSlice'

import { ExtensionContext } from '@looker/extension-sdk-react'
import process from 'process'
import { useErrorBoundary } from 'react-error-boundary'
import { RootState } from '../store'

export const useBigQueryExamples = () => {
  const connectionName = process.env.BIGQUERY_EXAMPLE_PROMPTS_CONNECTION_NAME || ''
  const datasetName = process.env.BIGQUERY_EXAMPLE_PROMPTS_DATASET_NAME || 'explore_assistant'

  const dispatch = useDispatch()
  const { showBoundary } = useErrorBoundary()
  const { isBigQueryMetadataLoaded } = useSelector((state: RootState) => state.assistant as AssistantState)

  const { core40SDK } = useContext(ExtensionContext)

  const runSQLQuery = async (sql: string) => {
    console.log('DEBUG: sql to run: ', sql);
    try {
      const createSqlQuery = await core40SDK.ok(
        core40SDK.create_sql_query({
          connection_name: connectionName,
          sql: sql,
        }),
      )
      console.log('DEBUG: BQ job created: ', createSqlQuery);
      
      const { slug } = await createSqlQuery
      if (slug) {
        const runSQLQuery = await core40SDK.ok(
          core40SDK.run_sql_query(slug, 'json'),
        )
        const examples = await runSQLQuery
        console.log('DEBUG: slug created: ', slug);
        return examples
      }
          return []
    } catch(error) {
      showBoundary(error)
      throw new Error('error')
    }
  }

  const getExamplePrompts = async () => {
    const sql = `
      SELECT
          explore_id,
          examples
      FROM
        \`${datasetName}.explore_assistant_examples\`
    `
    return runSQLQuery(sql).then((response) => {
      if(response.length === 0 || !Array.isArray(response)) {
        return
      }
      const generationExamples: ExploreExamples = {}
      if(response.length === 0 || !Array.isArray(response)) {
        return
      }
      response.forEach((row: any) => {
        generationExamples[row['explore_id']] = JSON.parse(row['examples'])
      })
      dispatch(setExploreGenerationExamples(generationExamples))
    }).catch((error) => showBoundary(error))
  }

  const getRefinementPrompts = async () => {
    const sql = `
    SELECT
        explore_id,
        examples
    FROM
      \`${datasetName}.explore_assistant_refinement_examples\`
  `
    return runSQLQuery(sql).then((response) => {
      if(response.length === 0 || !Array.isArray(response)) {
        return
      }
      const refinementExamples: RefinementExamples = {}
      if(response.length === 0 || !Array.isArray(response)) {
        return
      }
      response.forEach((row: any) => {
        refinementExamples[row['explore_id']] = JSON.parse(row['examples'])
      })
      dispatch(setExploreRefinementExamples(refinementExamples))
    }).catch((error) => showBoundary(error))
  }

  const getSamples = async () => {
    const sql = `
      SELECT
          explore_id,
          samples
      FROM
        \`${datasetName}.explore_assistant_samples\`
    `
    return runSQLQuery(sql).then((response) => {
      const exploreSamples: ExploreSamples = {}
      if(response.length === 0 || !Array.isArray(response)) {
        return
      }
      response.forEach((row: any) => {
        exploreSamples[row['explore_id']] = JSON.parse(row['samples'])
      })
      const exploreKey: string = response[0]['explore_id']
      const [modelName, exploreId] = exploreKey.split(':')
      dispatch(setExploreSamples(exploreSamples))
      dispatch(setCurrenExplore({
        exploreKey,
        modelName,
        exploreId
      }))
    }).catch((error) => showBoundary(error))
  }

  const getFeedbackCategories = async () => {
    const sql = `
    SELECT
        name,
        description
    FROM
      \`${datasetName}.feedback_categories\`
  `
    return runSQLQuery(sql).then((response) => {
      if(response.length === 0 || !Array.isArray(response)) {
        return
      }
      const feedbackCategories: FeedbackCategory[] = []
      
      if(response.length === 0 || !Array.isArray(response)) {
        return
      }

      response.forEach((row: any) => {
        feedbackCategories.push({
          name: row['name'],
          description: row['description']
        })
      })

      dispatch(setFeedbackCategories(feedbackCategories))
    }).catch((error) => showBoundary(error))
  }


  // Create a ref to track if the hook has already been called
  const hasFetched = useRef(false)

  // get the example prompts provide completion status
  useEffect(() => {
    if (hasFetched.current) return
    hasFetched.current = true

    // if we already fetch everything, return
    if(isBigQueryMetadataLoaded) return

    dispatch(setisBigQueryMetadataLoaded(false))
    Promise.all([getExamplePrompts(), getRefinementPrompts(), getSamples(), getFeedbackCategories()])
      .then(() => {
        dispatch(setisBigQueryMetadataLoaded(true))
      })
      .catch((error) => {
        showBoundary(error)
        dispatch(setisBigQueryMetadataLoaded(false))
      })
  }, [showBoundary])
}
