import React, { useState, useCallback, useEffect } from 'react'
import { useDispatch, useSelector } from 'react-redux';
import MarkdownText from './MarkdownText'
import clsx from 'clsx'
import { ThumbUp, ThumbDown } from '@material-ui/icons'
import './Message.css'
import process from 'process'
import { RootState, AssistantState } from '../../store'

export const getRelativeTimeString = (dateStr: string | Date) => {
  const date = new Date(dateStr)
  const now = new Date()

  const diffInSeconds = Math.floor((now.getTime() - date.getTime()) / 1000)
  const diffInMinutes = Math.floor(diffInSeconds / 60)
  const diffInHours = Math.floor(diffInMinutes / 60)
  const diffInDays = Math.floor(diffInHours / 24)

  // Function to format the date as "Oct 25, 2023"
  const formatDate = (date: Date) => {
    const options: Intl.DateTimeFormatOptions = {
      month: 'short', // allowed values: 'numeric', '2-digit', 'long', 'short', 'narrow'
      day: 'numeric', // allowed values: 'numeric', '2-digit'
      year: 'numeric', // allowed values: 'numeric', '2-digit'
    }
    return date.toLocaleDateString('en-US', options)
  }

  let relativeTime

  if (diffInSeconds < 1) {
    relativeTime = 'just now'
  } else if (diffInSeconds < 60) {
    relativeTime =
      diffInSeconds === 1 ? '1 second ago' : `${diffInSeconds} seconds ago`
  } else if (diffInMinutes < 60) {
    relativeTime =
      diffInMinutes === 1 ? '1 minute ago' : `${diffInMinutes} minutes ago`
  } else if (diffInHours < 24) {
    relativeTime = diffInHours === 1 ? '1 hour ago' : `${diffInHours} hours ago`
  } else if (diffInDays <= 2) {
    relativeTime = diffInDays === 1 ? '1 day ago' : `${diffInDays} days ago`
  } else {
    relativeTime = formatDate(date)
  }

  return relativeTime
}

export const getDateCategory = (date: Date) => {
  const now = new Date()
  const threadDate = new Date(date)

  const diffTime = Math.abs(now.getTime() - threadDate.getTime())
  const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24)) // difference in days

  if (diffDays === 1) {
    return 'Today'
  }
  if (diffDays === 2) {
    return 'Yesterday'
  }
  if (diffDays <= 7) {
    return 'Last 7 days'
  }
  if (diffDays <= 30) {
    return 'Last 30 days'
  }
  return 'More than 30 days ago'
}

interface MessageProps {
  actor: string
  children?: React.ReactNode
  createdAt?: number
  message?: string
  uuid: string
  feedback?: {
    feedback_text: string
    is_positive: boolean
  } | null
}

const Message = ({ message, actor, children, uuid, feedback }: MessageProps) => {
  const [isThumbUpClicked, setIsThumbUpClicked] = useState(false)
  const [isThumbDownClicked, setIsThumbDownClicked] = useState(false)
  const [showButtons, setShowButtons] = useState(false)
  const [feedbackVisible, setFeedbackVisible] = useState(false)
  const [feedbackText, setFeedbackText] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [selectedCategory, setSelectedCategory] = useState('')
  const [hasFeedback, setHasFeedback] = useState(false)
  const { me, currentExploreThread, feedbackCategories } = useSelector((state: RootState) => state.assistant as AssistantState)
  const { access_token } = useSelector((state: RootState) => state.auth)
  const VERTEX_AI_ENDPOINT = process.env.VERTEX_AI_ENDPOINT || ''
  const userId = me.id

  // doesnt do anything for now cause feeback prop dont persist but instead hasFeedBack, isThumbsUpClicked, isThumbsDownClicked.
  // use this in the future to persist feedback state in UI across sessions.
  useEffect(() => {
    if (feedback) {
      setHasFeedback(true)
      setIsThumbUpClicked(feedback.is_positive)
      setIsThumbDownClicked(!feedback.is_positive)
    }
  }, [feedback])

  const handleThumbUpClick = () => {
    if (hasFeedback) return
    setIsThumbUpClicked(!isThumbUpClicked)
    setIsThumbDownClicked(false)
    setFeedbackVisible(!isThumbUpClicked) // Show feedback form
    // You can also implement logic to track thumb up votes here, e.g., update state or send a feedback event
  }
  
  const handleThumbDownClick = () => {
    if (hasFeedback) return
    setIsThumbDownClicked(!isThumbDownClicked)
    setIsThumbUpClicked(false)
    setFeedbackVisible(!isThumbDownClicked) // Show feedback form
    // You can also implement logic to track thumb down votes here
  }

  const handleMouseEnter = () => {
    if (!hasFeedback) {
      setShowButtons(true)
    }
  }

  const handleMouseLeave = () => {
    if (!hasFeedback) {
      setTimeout(() => {
        setShowButtons(false)
      }, 100)
    }
  }

  const handleSubmitFeedback = useCallback(async () => {
    if (!uuid || !userId || !feedbackText) return

    setIsSubmitting(true)
    try {
      const response = await fetch(`${VERTEX_AI_ENDPOINT}/feedback`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${access_token}`,
        },
        body: JSON.stringify({
          user_id: userId,
          message_id: uuid,
          feedback_text: feedbackText,
          is_positive: isThumbUpClicked,
          category: selectedCategory,
        }),
      })

      if (!response.ok) {
        throw new Error('Failed to submit feedback')
      }

      setFeedbackVisible(false)
      setFeedbackText('')
      setHasFeedback(true)
    } catch (error) {
      console.error('Error submitting feedback:', error)
      // You might want to show an error message to the user here
    } finally {
      setIsSubmitting(false)
    }
  }, [feedbackText,uuid])

  const handleCancelFeedback = () => {
    setFeedbackVisible(false)
    setFeedbackText('')
    setIsThumbUpClicked(false)
    setIsThumbDownClicked(false)
  }

  return (
    <div
      className={`flex ${
        actor === 'user' ? 'justify-end' : 'justify-start'
      } mb-4`}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      <div className={`max-w-[70%] ${actor === 'user' ? 'order-2' : 'order-1'}`}>
        <div
          className={clsx(
            'rounded-lg p-3 max-w-xl',
            actor === 'user'
              ? 'bg-[rgb(237,243,253)] text-gray-800'
              : 'bg-[rgb(242,242,242)] text-gray-800',
          )}
        >
          {message && <MarkdownText text={message} />}
          {children && <div>{children}</div>}
        </div>
        {actor !== 'user' && !hasFeedback && (
          <div className={`flex space-x-2 mt-2 ${showButtons || isThumbUpClicked || isThumbDownClicked ? 'visible' : 'hidden'}`}>
            <button 
              onClick={handleThumbUpClick}
              className="hover:bg-gray-100 p-1 rounded-full"
            >
              <ThumbUp color={isThumbUpClicked ? 'primary' : 'inherit'} />
            </button>
            <button 
              onClick={handleThumbDownClick}
              className="hover:bg-gray-100 p-1 rounded-full"
            >
              <ThumbDown color={isThumbDownClicked ? 'primary' : 'inherit'} />
            </button>
          </div>
        )}
        {actor !== 'user' && hasFeedback && (
          <div className="text-sm text-gray-500 mt-1">
            Feedback submitted
          </div>
        )}
        {feedbackVisible && !hasFeedback && (
          <div className="feedback-form">
            <select 
              value={selectedCategory}
              onChange={(e) => setSelectedCategory(e.target.value)}
              className="feedback-dropdown"
              aria-label="Feedback category"
            >
              <option value="">Category (hover for info)</option>
              {feedbackCategories.map((category) => (
                <option 
                  key={category.name} 
                  value={category.name}
                  title={category.description}
                >
                  {category.name}
                </option>
              ))}
            </select>            
            <textarea
              value={feedbackText}
              onChange={(e) => setFeedbackText(e.target.value)}
              placeholder="Please provide your feedback..."
              className="feedback-textarea"
            />
            <div className="flex justify-end space-x-2">
              <button 
                onClick={handleCancelFeedback} 
                className="cancel-btn"
                disabled={isSubmitting}
              >
                Cancel
              </button>
              <button 
                onClick={handleSubmitFeedback} 
                className="submit-btn"
                disabled={isSubmitting || !feedbackText.trim()}
              >
                {isSubmitting ? 'Submitting...' : 'Submit'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default Message