import React, { useEffect, useRef } from 'react'
import { IconButton, Tooltip } from '@mui/material'
import MenuIcon from '@mui/icons-material/Menu'
import SettingsIcon from '@mui/icons-material/Settings'
import AddIcon from '@mui/icons-material/Add'
import ChatBubbleOutline from '@mui/icons-material/ChatBubbleOutline'
import { useDispatch, useSelector } from 'react-redux'
import {
  clearHistory,
  ExploreThread,
  openSidePanel,
  resetChat,
  setCurrentThread,
  updateCurrentThreadWithSync,
  setIsChatMode,
  setSidePanelExploreUrl,
  AssistantState,
  newThreadState,
  resetChatNoNewThread,
  fetchUserThreads,
  fetchThreadMessages,
  resetThreadPagination,
  resetMessagePagination,
  softDeleteSpecificThreads,
  resetThreadHasMore
} from '../../slices/assistantSlice'
import { RootState, AppDispatch } from '../../store'
import SettingsModal from './Settings'
import { CircularProgress } from '@material-ui/core'

interface SidebarProps {
  expanded: boolean
  toggleDrawer: () => void
  endOfMessagesRef?: React.RefObject<HTMLDivElement>
}

const Sidebar = ({ expanded, toggleDrawer, endOfMessagesRef }: SidebarProps) => {
  const dispatch = useDispatch<AppDispatch>()
  const [isExpanded, setIsExpanded] = React.useState(expanded)
  const [isSettingsOpen, setIsSettingsOpen] = React.useState(false)
  const { 
    isChatMode, 
    isQuerying, 
    history, 
    currentExplore, 
    me,
    isLoadingThreads = false,
    messageFetchStatus = {},
    pagination,
    threadsInitialized = false
  } = useSelector(
    (state: RootState) => state.assistant as AssistantState,
  )
  const { isAuthenticated } = useSelector((state: RootState) => state.auth);

  // Fetch threads on initial load if history is empty and not yet initialized
  useEffect(() => {
    if (isAuthenticated && me && !threadsInitialized && !isLoadingThreads) {
      dispatch(resetThreadPagination());
      dispatch(fetchUserThreads({ limit: 15, offset: 0 }));
    }
  }, [isAuthenticated, me, threadsInitialized, isLoadingThreads, dispatch]);

  const handleClick = () => {
    if (expanded) {
      // closing
      setIsExpanded(false)
      setTimeout(() => toggleDrawer(), 100)
    } else {
      // opening
      toggleDrawer()
      setTimeout(() => setIsExpanded(true), 100)
    }
  }

  const canReset = isChatMode && !isQuerying

  const handleNewChat = () => {
    if (canReset && me) {
      dispatch(newThreadState(me))
        .unwrap()
        .then((newThread: ExploreThread | undefined) => {
          if (newThread) {
            dispatch(resetChat(newThread))
            dispatch(updateCurrentThreadWithSync({
              exploreId: currentExplore.exploreId,
              modelName: currentExplore.modelName,
              exploreKey: currentExplore.exploreKey,
            }))
          }
        })
    }
  }

  const handleHistoryClick = (thread: ExploreThread) => {
    // Reset message pagination for this thread
    dispatch(resetMessagePagination(thread.uuid));
    
    // Use existing logic to set the current thread
    dispatch(resetChatNoNewThread());
    dispatch(setCurrentThread(thread));
    dispatch(setIsChatMode(true));
    dispatch(setSidePanelExploreUrl(thread.exploreUrl));
    dispatch(openSidePanel());
    
    // Check if we need to fetch messages for this thread
    if (thread.messages.length === 0 && 
        (!messageFetchStatus || !messageFetchStatus[thread.uuid] || 
         messageFetchStatus[thread.uuid] !== 'pending')) {
      // Fetch initial messages with limit of 2
      dispatch(fetchThreadMessages({ 
        threadId: thread.uuid,
        limit: 10,
        offset: 0
      }));
    }
    
    // Use a longer delay to ensure messages are loaded and rendered
    setTimeout(() => {
      console.log('Attempting to scroll to end of messages');
      if (endOfMessagesRef?.current) {
        console.log('Ref found, scrolling');
        
        // Try to find the message container
        const messageContainer = document.querySelector('.flex-grow.overflow-y-auto');
        if (messageContainer) {
          console.log('Message container found, scrolling to bottom');
          messageContainer.scrollTop = messageContainer.scrollHeight;
        }
        
        // Also try the direct ref scroll
        endOfMessagesRef.current.scrollIntoView({ 
          behavior: 'smooth',
          block: 'end'
        });
      } else {
        console.log('End of messages ref not found');
      }
    }, 800); // Use a longer delay (800ms) to ensure everything is loaded
  };


  const isThreadMessagesLoading = (threadId: string) => {
    return messageFetchStatus && messageFetchStatus[threadId] === 'pending';
  };

  const handleClearHistory = () => {
    const threadIds = history.map(thread => parseInt(thread.uuid));
    
    if (threadIds.length > 0 && me) {
      dispatch(softDeleteSpecificThreads(threadIds))
        .unwrap()
        .then(() => {
          dispatch(clearHistory());
          dispatch(resetThreadPagination());
          dispatch(resetThreadHasMore())
          dispatch(newThreadState(me))
            .unwrap()
            .then((newThread: ExploreThread | undefined) => {
              if (newThread) {
                dispatch(resetChat(newThread))
                dispatch(updateCurrentThreadWithSync({
                  exploreId: currentExplore.exploreId,
                  modelName: currentExplore.modelName,
                  exploreKey: currentExplore.exploreKey,
                }))
              }
            })
        })
        .catch((error: Error) => {
          console.error('Failed to clear history:', error);
        });
    } else {
      dispatch(clearHistory());
      dispatch(resetThreadPagination());
    }
  };

  const handleLoadMoreThreads = () => {
    if (pagination && !isLoadingThreads && pagination.threads.hasMore) {
      dispatch(fetchUserThreads({
        limit: pagination.threads.limit,
        offset: pagination.threads.offset
      }));
    }
  };

  const handleLoadMoreMessages = (threadId: string) => {
    const threadPagination = pagination?.messages[threadId];
    
    if (threadPagination && threadPagination.hasMore && 
        messageFetchStatus[threadId] !== 'pending') {
      dispatch(fetchThreadMessages({
        threadId,
        limit: threadPagination.limit,
        offset: threadPagination.offset
      }));
    }
  };

  const sortedHistory = [...history].sort((a, b) => b.createdAt - a.createdAt) as ExploreThread[];


  return (
    <div
      className={`fixed inset-y-0 left-0 bg-[#f0f4f9] transition-all duration-300 ease-in-out flex flex-col ${
        expanded ? 'w-80' : 'w-16'
      } shadow-md`}
    >
      <div className="p-4 flex items-center">
        <Tooltip
          title={expanded ? 'Collapse Menu' : 'Expand Menu'}
          placement="bottom"
          arrow={false}
        >
          <IconButton onClick={handleClick} className="mr-2">
            <MenuIcon />
          </IconButton>
        </Tooltip>
      </div>
      <div className="p-4 flex items-center">
        <Tooltip title={'New Chat'} placement="bottom" arrow={false}>
          <div
            className={`
              mr-2 flex flex-row items-center

              ${
                canReset
                  ? 'cursor-pointer bg-gray-300 text-gray-600 hover:text-gray-700'
                  : 'bg-gray-200 text-gray-400'
              }

              rounded-full p-2

              transition-all duration-300 ease-in-out

            `}
            onClick={handleNewChat}
          >
            <AddIcon />

            <div
              className={`
                   whitespace-nowrap transition-all duration-300 ease-in-out
                  ${isExpanded ? 'mx-3 opacity-100' : 'opacity-0'}
                  `}
            >
              {isExpanded && 'New Chat'}
            </div>
          </div>
        </Tooltip>
      </div>
      <nav className="flex-grow overflow-y-auto mt-4 ml-6 text-sm">
        {isExpanded && (
          <div>
            <div className="mb-4 flex flex-row">
              <div className="flex-grow font-semibold">Recent</div>
              {history.length > 0 && (
                <div
                  className="px-4 text-xs text-gray-400 hover:underline cursor-pointer"
                  onClick={handleClearHistory}
                >
                  clear
                </div>
              )}
            </div>
            <div className="flex flex-col space-y-4">
              {isLoadingThreads && !threadsInitialized && (
                <div className="flex justify-center">
                  <CircularProgress size={20} className="text-gray-400" />
                </div>
              )}
              {threadsInitialized && history.length === 0 && (
                <div className="text-gray-400">No recent chats</div>
              )}
              {sortedHistory.map((item) => (
                <div key={'history-' + item.uuid}>
                  <Tooltip
                    title={item.summarizedPrompt}
                    placement="right"
                    arrow
                  >
                    <div
                      className={`flex items-center cursor-pointer hover:underline`}
                      onClick={() => handleHistoryClick(item)}
                    >
                      <div className="">
                        <ChatBubbleOutline
                          fontSize="small"
                          className="mr-2 text-gray-600"
                        />
                      </div>
                      <div className="line-clamp-1 flex-grow">
                        <span className="ml-3">{item.summarizedPrompt}</span>
                      </div>
                      {isThreadMessagesLoading(item.uuid) && (
                        <CircularProgress size={12} className="text-gray-400 ml-2" />
                      )}
                    </div>
                  </Tooltip>
                </div>
              ))}
              
              {/* Load More Threads Button */}
              {pagination && pagination.threads.hasMore && (
                <div className="flex justify-center mt-4">
                  <button
                    onClick={handleLoadMoreThreads}
                    disabled={isLoadingThreads}
                    className="text-blue-500 hover:text-blue-700 px-4 py-2 rounded"
                  >
                    {isLoadingThreads ? (
                      <CircularProgress size={16} className="mr-2" />
                    ) : null}
                    Load More
                  </button>
                </div>
              )}
            </div>
          </div>
        )}
      </nav>
      <div className="mt-auto p-4 border-t">
        <Tooltip title={expanded ? '' : 'Settings'} placement="top" arrow>
          <div
            className={`mr-2 flex flex-row text-gray-400 items-center cursor-pointer p-2 transition-all duration-300 ease-in-out`}
            onClick={() => setIsSettingsOpen(true)}
          >
            <SettingsIcon />
            <div
              className={`
                   whitespace-nowrap transition-all duration-300 ease-in-out
                  ${isExpanded ? 'mx-3 opacity-100' : 'opacity-0'}
                  `}
            >
              {isExpanded && 'Settings'}
            </div>
          </div>
        </Tooltip>
      </div>
      <SettingsModal
        open={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
      />
    </div>
  )
}

export default Sidebar