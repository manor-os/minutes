import React, { useState, useEffect } from 'react';
import { format } from 'date-fns';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { CalendarIcon, ClockIcon, MonitorIcon, DollarIcon, CheckCircleIcon, UserIcon, FileTextIcon, DownloadIcon, AlertCircleIcon, RefreshIcon, EditIcon, TrashIcon, CloseIcon, StarIcon, LoaderIcon, ExternalLinkIcon, ShareIcon, LinkIcon, MicIcon, MessageIcon } from './Icons';
import { IS_CLOUD } from '../config/edition';
import './MeetingDetail.css';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8002';

function MeetingDetail({ meeting, onClose, onUpdate, onDelete, onNotification }) {
  const [isEditing, setIsEditing] = useState(false);
  const [editedSummary, setEditedSummary] = useState(meeting.summary || '');
  const [isDeleting, setIsDeleting] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [editingActionIndex, setEditingActionIndex] = useState(null);
  const [editedActionItems, setEditedActionItems] = useState([]);
  const [isSavingActionItems, setIsSavingActionItems] = useState(false);
  const [creatingTicketIndex, setCreatingTicketIndex] = useState(null);
  const [staffList, setStaffList] = useState([]);
  const [isLoadingStaff, setIsLoadingStaff] = useState(false);
  const [assetsList, setAssetsList] = useState([]);
  const [isLoadingAssets, setIsLoadingAssets] = useState(false);
  const [showAssetSelection, setShowAssetSelection] = useState(null); // Index of action item for which to show asset selection
  const [tempSelectedAssetId, setTempSelectedAssetId] = useState(null);
  const [shareToken, setShareToken] = useState(meeting.share_token || null);
  const [showShareDialog, setShowShareDialog] = useState(false);
  const [isSharing, setIsSharing] = useState(false);
  const [audioUrl, setAudioUrl] = useState(null);
  const [isLoadingAudio, setIsLoadingAudio] = useState(false);
  const [chatQuestion, setChatQuestion] = useState('');
  const [chatMessages, setChatMessages] = useState([]);
  const [isChatting, setIsChatting] = useState(false);
  const formatDuration = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}m ${secs}s`;
  };

  const formatPlatform = (platform) => {
    const platformMap = {
      'google_meet': 'Google Meet',
      'zoom': 'Zoom',
      'teams': 'Microsoft Teams',
      'browser_extension': 'Browser Extension',
      'phone_recorder': 'Minutes Recorder'
    };
    return platformMap[platform] || platform || 'Unknown';
  };

  // Clean up audio object URL on unmount
  useEffect(() => {
    return () => {
      if (audioUrl) URL.revokeObjectURL(audioUrl);
    };
  }, [audioUrl]);

  const loadAudio = async () => {
    if (!meeting.audio_file || audioUrl) return;
    setIsLoadingAudio(true);
    try {
      const token = localStorage.getItem('auth_token');
      const response = await fetch(`${API_BASE_URL}/api/meetings/audio/${meeting.audio_file}`, {
        headers: token ? { 'Authorization': `Bearer ${token}` } : {},
      });
      if (response.ok) {
        const blob = await response.blob();
        setAudioUrl(URL.createObjectURL(blob));
      }
    } catch (e) {
      console.error('Failed to load audio:', e);
    } finally {
      setIsLoadingAudio(false);
    }
  };

  // Load staff list and assets on component mount (cloud only)
  useEffect(() => {
    if (IS_CLOUD) {
      loadStaffList();
      loadAssetsList();
    }
  }, []);

  const loadAssetsList = async () => {
    setIsLoadingAssets(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/meetings/assets`, {
        method: 'GET',
        headers: getAuthHeaders()
      });

      if (response.ok) {
        const result = await response.json();
        if (result.success && result.assets) {
          setAssetsList(result.assets);
        }
      }
    } catch (_) {
      // Silent — assets endpoint may not exist in community mode
    } finally {
      setIsLoadingAssets(false);
    }
  };

  const loadStaffList = async () => {
    setIsLoadingStaff(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/meetings/staff/list`, {
        method: 'GET',
        headers: getAuthHeaders()
      });

      if (response.ok) {
        const result = await response.json();
        if (result.success && result.staff) {
          setStaffList(result.staff);
        }
      }
    } catch (_) {
      // Silent — staff endpoint may not exist in community mode
    } finally {
      setIsLoadingStaff(false);
    }
  };

  // No need for formatSummary - using ReactMarkdown now

  // Handle edit summary
  const handleEditSummary = () => {
    setIsEditing(true);
    setEditedSummary(meeting.summary || '');
  };

  // Save edited summary
  const getAuthHeaders = () => {
    const token = localStorage.getItem('auth_token');
    return {
      'Content-Type': 'application/json',
      ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
    };
  };

  const handleSaveSummary = async () => {
    setIsSaving(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/meetings/${meeting.id}`, {
        method: 'PATCH',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          summary: editedSummary
        })
      });

      const result = await response.json();
      
      if (result.success) {
        setIsEditing(false);
        if (onUpdate) {
          onUpdate(result.meeting);
        }
      } else {
        console.error('Failed to update summary:', result.error || 'Unknown error');
      }
    } catch (error) {
      console.error('Error updating summary:', error);
    } finally {
      setIsSaving(false);
    }
  };

  // Cancel editing
  const handleCancelEdit = () => {
    setIsEditing(false);
    setEditedSummary(meeting.summary || '');
  };

  // Handle edit action item
  const handleEditActionItem = (index, item) => {
    const raw = typeof item === 'string' ? { task: item } : item;
    const task = raw.task || raw.description || raw.text || (typeof raw === 'string' ? raw : JSON.stringify(raw));
    const assignee = (typeof raw.assignee === 'object' ? JSON.stringify(raw.assignee) : raw.assignee) || 'TBD';
    const dueDate = (typeof raw.due_date === 'object' ? JSON.stringify(raw.due_date) : (raw.due_date || raw.deadline)) || 'TBD';
    
    const updated = [...editedActionItems];
    updated[index] = { task, assignee, due_date: dueDate };
    setEditedActionItems(updated);
    setEditingActionIndex(index);
  };

  // Cancel editing action item
  const handleCancelEditActionItem = (index) => {
    setEditingActionIndex(null);
    const updated = [...editedActionItems];
    updated[index] = null;
    setEditedActionItems(updated);
  };

  // Delete action item
  const handleDeleteActionItem = async (index) => {
    setIsSavingActionItems(true);
    try {
      const updatedActionItems = [...(meeting.action_items || [])];
      updatedActionItems.splice(index, 1); // Remove the item at index
      
      const response = await fetch(`${API_BASE_URL}/api/meetings/${meeting.id}`, {
        method: 'PATCH',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          action_items: updatedActionItems
        })
      });

      if (!response.ok) {
        let errorMessage = 'Failed to delete action item. Please try again.';
        try {
          const errorData = await response.json();
          errorMessage = errorData.detail || errorData.error || errorMessage;
          
          // Handle 404 specifically
          if (response.status === 404) {
            errorMessage = 'Meeting not found. It may have been deleted or you may not have access to it.';
          }
        } catch (e) {
          // If response is not JSON, use status text
          errorMessage = response.statusText || errorMessage;
        }
        
        console.error('Failed to delete action item:', errorMessage);
        if (onNotification) {
          onNotification({
            message: errorMessage,
            type: 'error'
          });
        }
        return;
      }

      const result = await response.json();
      
      if (result.success) {
        if (onUpdate) {
          onUpdate(result.meeting);
        }
        if (onNotification) {
          onNotification({
            message: 'Action item deleted successfully',
            type: 'success'
          });
        }
      } else {
        const errorMsg = result.error || result.detail || 'Unknown error';
        console.error('Failed to delete action item:', errorMsg);
        if (onNotification) {
          onNotification({
            message: `Failed to delete action item: ${errorMsg}`,
            type: 'error'
          });
        }
      }
    } catch (error) {
      console.error('Error deleting action item:', error);
      if (onNotification) {
        onNotification({
          message: `Error deleting action item: ${error.message || 'Please check your connection and try again.'}`,
          type: 'error'
        });
      }
    } finally {
      setIsSavingActionItems(false);
    }
  };

  // Save edited action item
  const handleSaveActionItem = async (index) => {
    setIsSavingActionItems(true);
    try {
      const updatedActionItems = [...(meeting.action_items || [])];
      const editedItem = editedActionItems[index];
      
      if (!editedItem) {
        if (onNotification) {
          onNotification({
            message: 'No changes to save',
            type: 'error'
          });
        }
        setIsSavingActionItems(false);
        return;
      }
      
      updatedActionItems[index] = {
        task: editedItem.task || '',
        assignee: editedItem.assignee || 'TBD',
        due_date: editedItem.due_date || 'TBD'
      };
      
      const response = await fetch(`${API_BASE_URL}/api/meetings/${meeting.id}`, {
        method: 'PATCH',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          action_items: updatedActionItems
        })
      });

      if (!response.ok) {
        let errorMessage = 'Failed to update action item. Please try again.';
        try {
          const errorData = await response.json();
          errorMessage = errorData.detail || errorData.error || errorMessage;
          
          // Handle 404 specifically
          if (response.status === 404) {
            errorMessage = 'Meeting not found. It may have been deleted or you may not have access to it.';
          }
        } catch (e) {
          // If response is not JSON, use status text
          errorMessage = response.statusText || errorMessage;
        }
        
        console.error('Failed to update action item:', errorMessage);
        if (onNotification) {
          onNotification({
            message: errorMessage,
            type: 'error'
          });
        }
        return;
      }

      const result = await response.json();
      
      if (result.success) {
        setEditingActionIndex(null);
        const updated = [...editedActionItems];
        updated[index] = null;
        setEditedActionItems(updated);
        if (onUpdate) {
          onUpdate(result.meeting);
        }
        if (onNotification) {
          onNotification({
            message: 'Action item updated successfully',
            type: 'success'
          });
        }
      } else {
        const errorMsg = result.error || result.detail || 'Unknown error';
        console.error('Failed to update action item:', errorMsg);
        if (onNotification) {
          onNotification({
            message: `Failed to update action item: ${errorMsg}`,
            type: 'error'
          });
        }
      }
    } catch (error) {
      console.error('Error updating action item:', error);
      if (onNotification) {
        onNotification({
          message: `Error updating action item: ${error.message || 'Please check your connection and try again.'}`,
          type: 'error'
        });
      }
    } finally {
      setIsSavingActionItems(false);
    }
  };

  // Show asset selection modal
  const handleShowAssetSelection = (index) => {
    setShowAssetSelection(index);
    setTempSelectedAssetId(null);
  };

  // Create ticket from action item
  const handleCreateTicket = async (index, selectedAssetId = null) => {
    setShowAssetSelection(null); // Close asset selection modal
    setCreatingTicketIndex(index);
    try {
      const requestBody = {};
      if (selectedAssetId) {
        requestBody.asset_id = selectedAssetId;
      }
      
      const response = await fetch(`${API_BASE_URL}/api/meetings/${meeting.id}/action-items/${index}/create-ticket`, {
        method: 'POST',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(requestBody)
      });

      // Read response text first, then try to parse as JSON
      const responseText = await response.text();
      let result = null;
      
      if (responseText) {
        try {
          result = JSON.parse(responseText);
        } catch (parseError) {
          // If not JSON, use text as error message
          console.error('Failed to parse response as JSON:', responseText);
        }
      }
      
      if (!response.ok) {
        // Try to get detailed error message
        let errorMsg = `HTTP ${response.status}: ${response.statusText || 'Bad Request'}`;
        
        if (result) {
          // Extract error message from result object
          if (typeof result === 'string') {
            errorMsg = result;
          } else if (typeof result === 'object') {
            errorMsg = result.detail || result.error || result.message || result.msg || result.errorMessage || 
                      (result.code ? `Error code: ${result.code}` : null) ||
                      JSON.stringify(result).substring(0, 200) || errorMsg;
          }
        } else if (responseText) {
          // Try to parse responseText if it's JSON
          try {
            const parsed = JSON.parse(responseText);
            if (typeof parsed === 'object') {
              errorMsg = parsed.detail || parsed.error || parsed.message || parsed.msg || 
                        JSON.stringify(parsed).substring(0, 200);
            } else {
              errorMsg = responseText.substring(0, 200);
            }
          } catch {
            errorMsg = responseText.substring(0, 200);
          }
        }
        
        // Ensure errorMsg is always a string
        if (typeof errorMsg !== 'string') {
          errorMsg = String(errorMsg) || 'Unknown error occurred';
        }
        
        console.error('Failed to create ticket:', {
          status: response.status,
          statusText: response.statusText,
          error: errorMsg,
          responseText: responseText,
          result: result
        });
        
        if (onNotification) {
          // Format error message for better readability (handle multi-line messages)
          const formattedError = errorMsg.replace(/\n/g, ' ').replace(/\s+/g, ' ').trim();
          // Check if this is a configuration error (DocumentGroup or asset related)
          const isConfigError = formattedError.toLowerCase().includes('documentgroup') || 
                                formattedError.toLowerCase().includes('asset') ||
                                formattedError.toLowerCase().includes('configure');
          onNotification({
            message: `Failed to create ticket: ${formattedError}`,
            type: 'error',
            duration: isConfigError ? 10000 : 5000 // Show longer for configuration errors
          });
        }
        return;
      }
      
      // If response is OK but result is null, try to parse again
      if (!result && responseText) {
        try {
          result = JSON.parse(responseText);
        } catch (e) {
          console.error('Failed to parse successful response:', responseText);
          result = { success: true, message: 'Ticket created successfully' };
        }
      }
      
      if (result.success) {
        if (onNotification) {
          onNotification({
            message: `Ticket created successfully in Manor system!${result.task_id ? ` Task ID: ${result.task_id}` : ''}`,
            type: 'success'
          });
        }
      } else {
        const errorMsg = result.error || result.detail || result.message || 'Unknown error';
        console.error('Failed to create ticket:', errorMsg);
        if (onNotification) {
          // Format error message for better readability
          const formattedError = errorMsg.replace(/\n/g, ' ').replace(/\s+/g, ' ').trim();
          // Check if this is a configuration error
          const isConfigError = formattedError.toLowerCase().includes('documentgroup') || 
                                formattedError.toLowerCase().includes('asset') ||
                                formattedError.toLowerCase().includes('configure');
          onNotification({
            message: `Failed to create ticket: ${formattedError}`,
            type: 'error',
            duration: isConfigError ? 10000 : 5000 // Show longer for configuration errors
          });
        }
      }
    } catch (error) {
      console.error('Error creating ticket:', error);
      if (onNotification) {
        onNotification({
          message: `Error creating ticket: ${error.message || 'Please check your connection and try again.'}`,
          type: 'error'
        });
      }
    } finally {
      setCreatingTicketIndex(null);
    }
  };

  // Generate tickets for all action items
  const handleGenerateAllTickets = async () => {
    if (!meeting.action_items || meeting.action_items.length === 0) {
      if (onNotification) {
        onNotification({
          message: 'No action items to generate tickets for.',
          type: 'info'
        });
      }
      return;
    }
    
    setCreatingTicketIndex(-1); // Use -1 to indicate "all"
    
    try {
      const results = [];
      // Use the selected asset for all tickets (from modal or parameter)
      const assetIdToUse = selectedAssetId !== undefined ? selectedAssetId : tempSelectedAssetId;
      
      for (let i = 0; i < meeting.action_items.length; i++) {
        try {
          const requestBody = {};
          if (assetIdToUse) {
            requestBody.asset_id = assetIdToUse;
          }
          
          const response = await fetch(`${API_BASE_URL}/api/meetings/${meeting.id}/action-items/${i}/create-ticket`, {
            method: 'POST',
            headers: {
              ...getAuthHeaders(),
              'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestBody)
          });
          
          let result;
          let responseText = '';
          try {
            responseText = await response.text();
            if (responseText) {
              try {
                result = JSON.parse(responseText);
              } catch (parseError) {
                result = { detail: responseText || `HTTP ${response.status}: ${response.statusText}` };
              }
            } else {
              result = { detail: `HTTP ${response.status}: ${response.statusText}` };
            }
          } catch (error) {
            result = { detail: `Server error: ${response.status} ${response.statusText}` };
          }
          
          if (response.ok && result.success) {
            results.push({ index: i, success: true, error: null });
          } else {
            const errorMsg = result?.detail || result?.error || result?.message || result?.msg || `HTTP ${response.status}: ${response.statusText}`;
            results.push({ index: i, success: false, error: errorMsg });
          }
        } catch (error) {
          results.push({ index: i, success: false, error: error.message || 'Network error' });
        }
      }
      
      const successCount = results.filter(r => r.success).length;
      const failCount = results.length - successCount;
      
      if (failCount === 0) {
        if (onNotification) {
          onNotification({
            message: `Successfully created ${successCount} ticket(s) in Manor system!`,
            type: 'success'
          });
        }
      } else {
        // Check if any failures are due to configuration issues
        const configErrors = results.filter(r => !r.success && r.error && 
          (r.error.toLowerCase().includes('documentgroup') || 
           r.error.toLowerCase().includes('asset') ||
           r.error.toLowerCase().includes('configure')));
        
        if (onNotification) {
          let errorMessage = `Created ${successCount} ticket(s), ${failCount} failed.`;
          if (configErrors.length > 0) {
            errorMessage += ' Some tickets require DocumentGroup and asset configuration in Manor system.';
          }
          onNotification({
            message: errorMessage,
            type: 'error',
            duration: configErrors.length > 0 ? 10000 : 5000
          });
        }
        console.error('Ticket creation results:', results);
      }
    } catch (error) {
      console.error('Error generating tickets:', error);
      if (onNotification) {
        onNotification({
          message: `Error generating tickets: ${error.message || 'Please try again.'}`,
          type: 'error'
        });
      }
    } finally {
      setCreatingTicketIndex(null);
    }
  };

  // Handle delete meeting
  const handleDelete = async () => {
    // Silent delete - no confirmation popup
    setIsDeleting(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/meetings/${meeting.id}`, {
        method: 'DELETE',
        headers: getAuthHeaders()
      });

      const result = await response.json();
      
      if (result.success) {
        if (onDelete) {
          onDelete(meeting.id);
        }
        onClose();
      } else {
        console.error('Failed to delete meeting:', result.error || 'Unknown error');
      }
    } catch (error) {
      console.error('Error deleting meeting:', error);
    } finally {
      setIsDeleting(false);
    }
  };

  // Download as text file
  const downloadAsText = () => {
    const content = `MEETING NOTES
${'='.repeat(50)}

Title: ${meeting.title || 'Untitled Meeting'}
Date: ${format(new Date(meeting.created_at), 'MMMM dd, yyyy HH:mm')}
Duration: ${meeting.duration ? formatDuration(meeting.duration) : 'N/A'}
Platform: ${formatPlatform(meeting.platform)}
${meeting.token_cost && meeting.token_cost.total_cost > 0 ? `Total Cost: $${meeting.token_cost.total_cost.toFixed(4)} USD` : ''}

${'='.repeat(50)}

SUMMARY
${'-'.repeat(50)}
${meeting.summary || 'No summary available'}

${'='.repeat(50)}

KEY POINTS
${'-'.repeat(50)}
${meeting.key_points && meeting.key_points.length > 0
  ? meeting.key_points.map((point, i) => `${i + 1}. ${typeof point === 'string' ? point : (point.text || point.description || JSON.stringify(point))}`).join('\n')
  : 'No key points available'}

${'='.repeat(50)}

ACTION ITEMS
${'-'.repeat(50)}
${meeting.action_items && meeting.action_items.length > 0
  ? meeting.action_items.map((item, i) => {
      const raw = typeof item === 'string' ? { task: item } : item;
      const task = raw.task || raw.description || raw.text || JSON.stringify(raw);
      const assignee = typeof raw.assignee === 'object' ? JSON.stringify(raw.assignee) : (raw.assignee || 'TBD');
      const dueDate = typeof raw.due_date === 'object' ? JSON.stringify(raw.due_date) : (raw.due_date || raw.deadline || 'TBD');
      return `${i + 1}. ${task}\n   Assignee: ${assignee}\n   Due Date: ${dueDate}`;
    }).join('\n\n')
  : 'No action items available'}

${'='.repeat(50)}

TRANSCRIPT
${'-'.repeat(50)}
${meeting.transcript || 'No transcript available'}

${'='.repeat(50)}
Generated by Minutes
`;

    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${meeting.title || 'meeting'}_${format(new Date(meeting.created_at), 'yyyy-MM-dd')}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  // Download as PDF (using browser print)
  const downloadAsPDF = () => {
    const printWindow = window.open('', '_blank');
    const content = `
<!DOCTYPE html>
<html>
<head>
  <title>${meeting.title || 'Meeting Notes'}</title>
  <style>
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      max-width: 800px;
      margin: 40px auto;
      padding: 20px;
      line-height: 1.6;
      color: #333;
    }
    h1 { color: #2196F3; border-bottom: 2px solid #2196F3; padding-bottom: 10px; }
    h2 { color: #1976D2; margin-top: 30px; }
    h3 { color: #424242; margin-top: 20px; }
    .meta { background: #f5f5f5; padding: 15px; border-radius: 8px; margin: 20px 0; }
    .meta-item { display: block; margin: 5px 0; }
    .section { margin: 30px 0; }
    .summary { white-space: pre-wrap; line-height: 1.8; }
    .key-points ul, .action-items ul { padding-left: 20px; }
    .key-points li, .action-items li { margin: 10px 0; }
    .action-item { background: #f8f9fa; padding: 10px; margin: 10px 0; border-left: 3px solid #4CAF50; }
    .transcript { background: #fafafa; padding: 15px; border-radius: 8px; white-space: pre-wrap; font-size: 12px; }
    @media print {
      body { margin: 0; }
      .no-print { display: none; }
    }
  </style>
</head>
<body>
  <h1>${meeting.title || 'Meeting Notes'}</h1>
  
  <div class="meta">
    <span class="meta-item"><strong>Date:</strong> ${format(new Date(meeting.created_at), 'MMMM dd, yyyy HH:mm')}</span>
    <span class="meta-item"><strong>Duration:</strong> ${meeting.duration ? formatDuration(meeting.duration) : 'N/A'}</span>
    <span class="meta-item"><strong>Platform:</strong> ${formatPlatform(meeting.platform)}</span>
    ${meeting.token_cost && meeting.token_cost.total_cost > 0 ? `<span class="meta-item"><strong>Total Cost:</strong> $${meeting.token_cost.total_cost.toFixed(4)} USD</span>` : ''}
  </div>

  ${meeting.summary ? `
  <div class="section">
    <h2>Summary</h2>
    <div class="summary">${meeting.summary.replace(/\n/g, '<br>')}</div>
  </div>
  ` : ''}

  ${meeting.key_points && meeting.key_points.length > 0 ? `
  <div class="section key-points">
    <h2>Key Points</h2>
    <ul>
      ${meeting.key_points.map(point => `<li>${typeof point === 'string' ? point : (point.text || point.description || JSON.stringify(point))}</li>`).join('')}
    </ul>
  </div>
  ` : ''}

  ${meeting.action_items && meeting.action_items.length > 0 ? `
  <div class="section action-items">
    <h2>Action Items</h2>
    <ul>
      ${meeting.action_items.map(item => {
        const raw = typeof item === 'string' ? { task: item } : item;
        const task = raw.task || raw.description || raw.text || JSON.stringify(raw);
        const assignee = typeof raw.assignee === 'object' ? JSON.stringify(raw.assignee) : (raw.assignee || 'TBD');
        const dueDate = typeof raw.due_date === 'object' ? JSON.stringify(raw.due_date) : (raw.due_date || raw.deadline || 'TBD');
        return `<li class="action-item"><strong>${task}</strong><br>Assignee: ${assignee} | Due: ${dueDate}</li>`;
      }).join('')}
    </ul>
  </div>
  ` : ''}

  ${meeting.transcript ? `
  <div class="section">
    <h2>Full Transcript</h2>
    <div class="transcript">${meeting.transcript}</div>
  </div>
  ` : ''}

  <div class="no-print" style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #ddd; text-align: center; color: #999; font-size: 12px;">
    Generated by Minutes
  </div>
</body>
</html>
    `;
    
    printWindow.document.write(content);
    printWindow.document.close();
    
    setTimeout(() => {
      printWindow.print();
    }, 250);
  };

  // Share meeting
  const handleShare = async () => {
    if (shareToken) {
      setShowShareDialog(true);
      return;
    }
    setIsSharing(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/meetings/${meeting.id}/share`, {
        method: 'POST',
        headers: getAuthHeaders(),
      });
      const result = await response.json();
      if (result.success) {
        setShareToken(result.share_token);
        setShowShareDialog(true);
      } else {
        if (onNotification) onNotification({ message: 'Failed to create share link', type: 'error' });
      }
    } catch (error) {
      console.error('Error creating share link:', error);
      if (onNotification) onNotification({ message: 'Failed to create share link', type: 'error' });
    } finally {
      setIsSharing(false);
    }
  };

  const handleRevokeShare = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/meetings/${meeting.id}/share`, {
        method: 'DELETE',
        headers: getAuthHeaders(),
      });
      const result = await response.json();
      if (result.success) {
        setShareToken(null);
        setShowShareDialog(false);
        if (onNotification) onNotification({ message: 'Share link revoked', type: 'success' });
      }
    } catch (error) {
      console.error('Error revoking share link:', error);
      if (onNotification) onNotification({ message: 'Failed to revoke share link', type: 'error' });
    }
  };

  const handleCopyShareLink = () => {
    const url = `${window.location.origin}/shared/${shareToken}`;
    navigator.clipboard.writeText(url).then(() => {
      if (onNotification) onNotification({ message: 'Share link copied to clipboard!', type: 'success' });
    }).catch(() => {
      // Fallback
      const input = document.createElement('input');
      input.value = url;
      document.body.appendChild(input);
      input.select();
      document.execCommand('copy');
      document.body.removeChild(input);
      if (onNotification) onNotification({ message: 'Share link copied to clipboard!', type: 'success' });
    });
  };

  const handleChat = async () => {
    if (!chatQuestion.trim() || isChatting) return;
    const q = chatQuestion.trim();
    setChatMessages(prev => [...prev, { role: 'user', content: q }]);
    setChatQuestion('');
    setIsChatting(true);

    // Add empty assistant message that will be streamed into
    const msgIndex = chatMessages.length + 1; // +1 for the user msg we just added
    setChatMessages(prev => [...prev, { role: 'assistant', content: '' }]);

    try {
      const authToken = localStorage.getItem('auth_token');
      const response = await fetch(`${API_BASE_URL}/api/meetings/${meeting.id}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(authToken ? { 'Authorization': `Bearer ${authToken}` } : {}),
        },
        body: JSON.stringify({ question: q }),
      });

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const data = JSON.parse(line.slice(6));
            if (data.token) {
              setChatMessages(prev => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                if (last && last.role === 'assistant') {
                  updated[updated.length - 1] = { ...last, content: last.content + data.token };
                }
                return updated;
              });
            }
            if (data.error) {
              setChatMessages(prev => {
                const updated = [...prev];
                updated[updated.length - 1] = { role: 'assistant', content: 'Sorry, failed to generate an answer.' };
                return updated;
              });
            }
          } catch {}
        }
      }
    } catch {
      setChatMessages(prev => {
        const updated = [...prev];
        if (updated[updated.length - 1]?.role === 'assistant' && !updated[updated.length - 1]?.content) {
          updated[updated.length - 1] = { role: 'assistant', content: 'Failed to get answer. Please try again.' };
        }
        return updated;
      });
    } finally {
      setIsChatting(false);
    }
  };

  if (!meeting) return null;

  return (
    <div className="meeting-detail-overlay" onClick={onClose}>
      <div className="meeting-detail-modal" onClick={(e) => e.stopPropagation()}>
        {/* Fixed header */}
        <div className="detail-header">
          <div className="detail-header-left">
            <h2>{meeting.title || 'Untitled Meeting'}</h2>
            <div className="detail-header-meta">
              <span><CalendarIcon size={12} /> {format(new Date(meeting.created_at), 'MMM dd, yyyy · HH:mm')}</span>
              {meeting.duration > 0 && <span><ClockIcon size={12} /> {formatDuration(meeting.duration)}</span>}
              {meeting.platform && <span><MonitorIcon size={12} /> {formatPlatform(meeting.platform)}</span>}
              {meeting.token_cost?.total_cost > 0 && <span><DollarIcon size={12} /> ${meeting.token_cost.total_cost.toFixed(4)}</span>}
            </div>
          </div>
          <button className="btn-close" onClick={onClose}><CloseIcon size={18} /></button>
        </div>

        {/* Scrollable content */}
        <div className="detail-body">

        {meeting.audio_file && (
          <div className="detail-section audio-section">
            <h3 className="section-title"><MicIcon size={16} /> Audio Recording</h3>
            {audioUrl ? (
              <audio controls src={audioUrl} className="audio-player" />
            ) : (
              <button className="btn-load-audio" onClick={loadAudio} disabled={isLoadingAudio}>
                {isLoadingAudio ? 'Loading audio...' : 'Load Audio Player'}
              </button>
            )}
          </div>
        )}

        {meeting.token_cost && meeting.token_cost.total_cost > 0 && (
          <div className="detail-section">
            <h3 className="section-title"><DollarIcon size={14} /> Token Usage & Cost</h3>
            <div className="token-cost-info">
              {meeting.token_cost.transcription && (
                <div className="cost-item">
                  <strong>Transcription (Whisper):</strong>
                  <span>{meeting.token_cost.transcription.duration_minutes?.toFixed(2) || 0} min</span>
                  <span className="cost">${meeting.token_cost.transcription.cost?.toFixed(4) || 0}</span>
                </div>
              )}
              {meeting.token_cost.summarization && (
                <>
                  <div className="cost-item">
                    <strong>Summary:</strong>
                    <span>{meeting.token_cost.summarization.summary?.tokens || 0} tokens</span>
                    <span className="cost">${meeting.token_cost.summarization.summary?.cost?.toFixed(4) || 0}</span>
                  </div>
                  <div className="cost-item">
                    <strong>Key Points:</strong>
                    <span>{meeting.token_cost.summarization.key_points?.tokens || 0} tokens</span>
                    <span className="cost">${meeting.token_cost.summarization.key_points?.cost?.toFixed(4) || 0}</span>
                  </div>
                  <div className="cost-item">
                    <strong>Action Items:</strong>
                    <span>{meeting.token_cost.summarization.action_items?.tokens || 0} tokens</span>
                    <span className="cost">${meeting.token_cost.summarization.action_items?.cost?.toFixed(4) || 0}</span>
                  </div>
                </>
              )}
              <div className="cost-total">
                <strong>Total Cost:</strong>
                <span className="total-cost">${meeting.token_cost.total_cost?.toFixed(4) || 0} USD</span>
              </div>
            </div>
          </div>
        )}

        {meeting.summary && (
          <div className="detail-section">
            <div className="section-header">
              <h3 className="section-title"><FileTextIcon size={16} /> Summary</h3>
              {!isEditing && (
                <button className="btn-edit" onClick={handleEditSummary}>
                  <EditIcon size={14} /> Edit
                </button>
              )}
            </div>
            {isEditing ? (
              <div className="edit-summary">
                <textarea
                  className="summary-textarea"
                  value={editedSummary}
                  onChange={(e) => setEditedSummary(e.target.value)}
                  rows={15}
                  placeholder="Enter meeting summary..."
                />
                <div className="edit-actions">
                  <button 
                    className="btn-save" 
                    onClick={handleSaveSummary}
                    disabled={isSaving}
                  >
                    {isSaving ? 'Saving...' : <><CheckCircleIcon size={14} /> Save</>}
                  </button>
                  <button 
                    className="btn-cancel" 
                    onClick={handleCancelEdit}
                    disabled={isSaving}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div className="summary-content markdown-body">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {meeting.summary}
                </ReactMarkdown>
              </div>
            )}
          </div>
        )}

        {meeting.key_points && meeting.key_points.length > 0 && (
          <div className="detail-section">
            <h3 className="section-title"><StarIcon size={16} /> Key Points</h3>
            <ul className="key-points-list">
              {meeting.key_points.map((point, index) => (
                <li key={index}>{typeof point === 'string' ? point : (point.text || point.description || point.point || JSON.stringify(point))}</li>
              ))}
            </ul>
          </div>
        )}

        {meeting.action_items && meeting.action_items.length > 0 && (
          <div className="detail-section">
            <div className="section-header">
              <h3 className="section-title"><CheckCircleIcon size={16} /> Action Items</h3>
              {IS_CLOUD && (
                <button
                  className="btn-generate-tickets"
                  onClick={() => handleGenerateAllTickets()}
                  disabled={creatingTicketIndex !== null}
                >
                  {creatingTicketIndex !== null ? <><LoaderIcon size={14} /> Creating...</> : <><ExternalLinkIcon size={14} /> Generate All Tickets</>}
                </button>
              )}
              {showAssetSelection === -1 && (
                <div className="asset-selection-modal">
                  <div className="asset-selection-content">
                    <h4>Select Asset for All Tickets (Optional)</h4>
                    <select
                      className="asset-select"
                      value={tempSelectedAssetId || ''}
                      onChange={(e) => setTempSelectedAssetId(e.target.value ? parseInt(e.target.value) : null)}
                    >
                      <option value="">No Asset (Leave blank)</option>
                      {assetsList.map((asset) => (
                        <option key={asset.id} value={asset.id}>
                          {asset.name}{asset.address ? ` - ${asset.address}` : ''}
                        </option>
                      ))}
                    </select>
                    <div className="asset-selection-actions">
                      <button
                        className="btn-confirm-asset"
                        onClick={() => handleGenerateAllTickets(tempSelectedAssetId)}
                        disabled={creatingTicketIndex !== null}
                      >
                        Generate All Tickets
                      </button>
                      <button
                        className="btn-cancel-asset"
                        onClick={() => setShowAssetSelection(null)}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
            <div className="action-items-list">
              {meeting.action_items.map((item, index) => {
                const raw = typeof item === 'string' ? { task: item } : item;
                const task = raw.task || raw.description || raw.text || (typeof raw === 'string' ? raw : JSON.stringify(raw));
                const assigneeRaw = raw.assignee || raw.assigned_to;
                const assignee = typeof assigneeRaw === 'object' ? JSON.stringify(assigneeRaw) : (assigneeRaw || 'TBD');
                const dueDateRaw = raw.due_date || raw.deadline;
                const dueDate = typeof dueDateRaw === 'object' ? JSON.stringify(dueDateRaw) : (dueDateRaw || 'TBD');
                const isEditing = editingActionIndex === index;
                const editedItem = editedActionItems[index] || { task, assignee, due_date: dueDate };
                
                return (
                  <div key={index} className={`action-item-card ${isEditing ? 'action-item-editing' : ''}`}>
                    {isEditing ? (
                      <div className="action-item-edit">
                        <input
                          type="text"
                          className="action-edit-task"
                          value={editedItem.task}
                          onChange={(e) => {
                            const updated = [...editedActionItems];
                            updated[index] = { ...editedItem, task: e.target.value };
                            setEditedActionItems(updated);
                          }}
                          placeholder="Task description"
                          autoFocus
                        />
                        <div className="action-edit-meta">
                          <div className="action-edit-field">
                            <label className="action-edit-label"><UserIcon size={14} /> Assignee</label>
                            <select
                              className="action-edit-assignee"
                              value={editedItem.assignee || 'TBD'}
                              onChange={(e) => {
                                const updated = [...editedActionItems];
                                updated[index] = { ...editedItem, assignee: e.target.value };
                                setEditedActionItems(updated);
                              }}
                            >
                              <option value="TBD">TBD</option>
                              {staffList.map((staff) => (
                                <option key={staff.id} value={staff.name}>
                                  {staff.name}{staff.title ? ` - ${staff.title}` : ''}
                                </option>
                              ))}
                            </select>
                          </div>
                          <div className="action-edit-field">
                            <label className="action-edit-label"><CalendarIcon size={14} /> Due Date</label>
                            <input
                              type="datetime-local"
                              className="action-edit-due"
                              value={(() => {
                                if (!editedItem.due_date || editedItem.due_date === 'TBD') {
                                  return '';
                                }
                                try {
                                  // If it already includes 'T', it's likely in ISO format
                                  if (editedItem.due_date.includes('T')) {
                                    return editedItem.due_date.substring(0, 16);
                                  }
                                  // Try to parse as date
                                  const date = new Date(editedItem.due_date);
                                  // Check if date is valid
                                  if (isNaN(date.getTime())) {
                                    return '';
                                  }
                                  return date.toISOString().substring(0, 16);
                                } catch (e) {
                                  // If parsing fails, return empty string
                                  return '';
                                }
                              })()}
                              onChange={(e) => {
                                const updated = [...editedActionItems];
                                const dateValue = e.target.value ? e.target.value : 'TBD';
                                updated[index] = { ...editedItem, due_date: dateValue };
                                setEditedActionItems(updated);
                              }}
                              placeholder="Select date and time"
                            />
                          </div>
                        </div>
                        <div className="action-edit-actions">
                          <button 
                            type="button"
                            className="btn-save-small" 
                            onClick={(e) => {
                              e.preventDefault();
                              e.stopPropagation();
                              handleSaveActionItem(index);
                            }}
                            disabled={isSavingActionItems}
                          >
                            <span className="btn-icon"><CheckCircleIcon size={14} /></span>
                            <span className="btn-text">{isSavingActionItems ? 'Saving...' : 'Save'}</span>
                          </button>
                          <button 
                            type="button"
                            className="btn-cancel-small" 
                            onClick={(e) => {
                              e.preventDefault();
                              e.stopPropagation();
                              handleCancelEditActionItem(index);
                            }}
                            disabled={isSavingActionItems}
                          >
                            <span className="btn-text">Cancel</span>
                          </button>
                        </div>
                      </div>
                    ) : (
                      <>
                        <div className="action-item-content">
                          <div className="action-task">{task}</div>
                          <div className="action-meta">
                            <span className="action-assignee">
                              <span className="action-icon"><UserIcon size={14} /></span>
                              <span className="action-label">Assignee:</span>
                              <span className="action-value">{assignee}</span>
                            </span>
                            <span className="action-due">
                              <span className="action-icon"><CalendarIcon size={14} /></span>
                              <span className="action-label">Due:</span>
                              <span className="action-value">{dueDate}</span>
                            </span>
                          </div>
                        </div>
                        <div className="action-item-actions">
                          <button 
                            className="btn-edit-small" 
                            onClick={() => handleEditActionItem(index, item)}
                            title="Edit this action item"
                          >
                            <span className="btn-icon"><EditIcon size={14} /></span>
                            <span className="btn-text">Edit</span>
                          </button>
                          {IS_CLOUD && (
                            <>
                              <button
                                className="btn-ticket-small"
                                onClick={() => {
                                  if (assetsList.length > 0) {
                                    handleShowAssetSelection(index);
                                  } else {
                                    handleCreateTicket(index, null);
                                  }
                                }}
                                disabled={creatingTicketIndex === index || creatingTicketIndex === -1}
                                title="Create a ticket in Manor system"
                              >
                                {creatingTicketIndex === index ? (
                                  <><span className="btn-icon"><LoaderIcon size={14} /></span><span className="btn-text">Creating...</span></>
                                ) : (
                                  <><span className="btn-icon"><ExternalLinkIcon size={14} /></span><span className="btn-text">Create Ticket</span></>
                                )}
                              </button>
                              {showAssetSelection === index && (
                                <div className="asset-selection-modal">
                                  <div className="asset-selection-content">
                                    <h4>Select Asset (Optional)</h4>
                                    <select
                                      className="asset-select"
                                      value={tempSelectedAssetId || ''}
                                      onChange={(e) => setTempSelectedAssetId(e.target.value ? parseInt(e.target.value) : null)}
                                    >
                                      <option value="">No Asset (Leave blank)</option>
                                      {assetsList.map((asset) => (
                                        <option key={asset.id} value={asset.id}>
                                          {asset.name}{asset.address ? ` - ${asset.address}` : ''}
                                        </option>
                                      ))}
                                    </select>
                                    <div className="asset-selection-actions">
                                      <button className="btn-confirm-asset" onClick={() => handleCreateTicket(index, tempSelectedAssetId)} disabled={creatingTicketIndex === index}>Create Ticket</button>
                                      <button className="btn-cancel-asset" onClick={() => setShowAssetSelection(null)}>Cancel</button>
                                    </div>
                                  </div>
                                </div>
                              )}
                            </>
                          )}
                          <button 
                            className="btn-delete-small" 
                            onClick={() => handleDeleteActionItem(index)}
                            disabled={isSavingActionItems}
                            title="Delete this action item"
                          >
                            <span className="btn-icon"><TrashIcon size={14} /></span>
                            <span className="btn-text">Delete</span>
                          </button>
                        </div>
                      </>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {meeting.transcript && (
          <div className="detail-section">
            <details className="transcript-section" open>
              <summary className="transcript-summary"><FileTextIcon size={16} /> Full Transcript</summary>
              <div className="transcript-content">
                {meeting.metadata?.speaker_segments ? (
                  <div className="transcript-lines">
                    {meeting.metadata.speaker_segments.map((segment, index) => (
                      <div key={index} className="transcript-line">
                        <div className="transcript-line-meta">
                          <span className="transcript-speaker">{segment.speaker || 'Speaker'}</span>
                          {segment.start != null && (
                            <span className="transcript-time">
                              {Math.floor(segment.start / 60)}:{String(Math.floor(segment.start % 60)).padStart(2, '0')}
                            </span>
                          )}
                        </div>
                        <div className="transcript-line-text">{segment.text}</div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="transcript-lines">
                    {meeting.transcript.split(/(?<=[.!?。！？\n])\s+/).filter(s => s.trim()).map((sentence, i) => (
                      <div key={i} className="transcript-line">
                        <div className="transcript-line-meta">
                          <span className="transcript-time">
                            {meeting.duration > 0
                              ? `${Math.floor((i / Math.max(meeting.transcript.split(/(?<=[.!?。！？\n])\s+/).filter(s => s.trim()).length) * meeting.duration) / 60)}:${String(Math.floor((i / Math.max(meeting.transcript.split(/(?<=[.!?。！？\n])\s+/).filter(s => s.trim()).length) * meeting.duration) % 60)).padStart(2, '0')}`
                              : `${i + 1}`}
                          </span>
                        </div>
                        <div className="transcript-line-text">{sentence.trim()}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </details>
          </div>
        )}

        {meeting.status === 'completed' && (
          <div className="detail-section chat-section">
            <h3 className="section-title"><MessageIcon size={16} /> Ask About This Meeting</h3>
            {chatMessages.length > 0 && (
              <div className="chat-messages">
                {chatMessages.map((msg, i) => (
                  <div key={i} className={`chat-msg chat-msg-${msg.role}`}>
                    <div className="chat-msg-content">
                      {msg.role === 'assistant' ? (
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                      ) : (
                        msg.content
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
            <div className="chat-input-row">
              <input
                type="text"
                className="chat-input"
                value={chatQuestion}
                onChange={(e) => setChatQuestion(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleChat()}
                placeholder="Ask a question about this meeting..."
                disabled={isChatting}
              />
              <button className="chat-send-btn" onClick={handleChat} disabled={isChatting || !chatQuestion.trim()}>
                {isChatting ? '...' : 'Ask'}
              </button>
            </div>
          </div>
        )}

        </div>{/* end detail-body */}

        {/* Share dialog */}
        {showShareDialog && (
          <div className="share-dialog-overlay" onClick={() => setShowShareDialog(false)}>
            <div className="share-dialog" onClick={(e) => e.stopPropagation()}>
              <div className="share-dialog-header">
                <h3><LinkIcon size={16} /> Share Meeting</h3>
                <button className="btn-close-share" onClick={() => setShowShareDialog(false)}>
                  <CloseIcon size={14} />
                </button>
              </div>
              <div className="share-dialog-body">
                <p className="share-description">Anyone with this link can view the meeting notes (read-only).</p>
                <div className="share-url-row">
                  <input
                    type="text"
                    readOnly
                    value={`${window.location.origin}/shared/${shareToken}`}
                    className="share-url-input"
                  />
                  <button className="btn-copy-link" onClick={handleCopyShareLink}>
                    Copy
                  </button>
                </div>
              </div>
              <div className="share-dialog-footer">
                <button className="btn-revoke-share" onClick={handleRevokeShare}>
                  Revoke Link
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Fixed footer actions */}
        <div className="detail-footer">
          <button className="btn-download-audio" onClick={() => {
            if (!meeting.audio_file) {
              if (onNotification) onNotification({ message: 'No audio file available', type: 'error' });
              return;
            }
            if (audioUrl) {
              const a = document.createElement('a');
              a.href = audioUrl;
              a.download = `${meeting.title || 'recording'}.webm`;
              a.click();
            } else {
              const token = localStorage.getItem('auth_token');
              fetch(`${API_BASE_URL}/api/meetings/audio/${meeting.audio_file}`, {
                headers: token ? { 'Authorization': `Bearer ${token}` } : {},
              }).then(r => {
                if (!r.ok) throw new Error('Download failed');
                return r.blob();
              }).then(blob => {
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `${meeting.title || 'recording'}.webm`;
                a.click();
                URL.revokeObjectURL(url);
              }).catch(() => {
                if (onNotification) onNotification({ message: 'Failed to download audio', type: 'error' });
              });
            }
          }}>
            <DownloadIcon size={14} /> Audio
          </button>
          <button className="btn-download-text" onClick={downloadAsText}>
            <FileTextIcon size={14} /> Text
          </button>
          <button className="btn-download-pdf" onClick={downloadAsPDF}>
            <DownloadIcon size={14} /> PDF
          </button>
          <button
            className="btn-share"
            onClick={handleShare}
            disabled={isSharing}
            title={shareToken ? 'Manage share link' : 'Create share link'}
          >
            {isSharing ? '...' : <><ShareIcon size={14} /> {shareToken ? 'Shared' : 'Share'}</>}
          </button>
          <div style={{ flex: 1 }} />
          <button
            className="btn-retry-detail"
            onClick={async () => {
              try {
                const token = localStorage.getItem('auth_token');
                const response = await fetch(`${API_BASE_URL}/api/meetings/${meeting.id}/retry`, {
                  method: 'POST',
                  headers: token ? { 'Authorization': `Bearer ${token}` } : {},
                });
                if (response.ok) {
                  if (onNotification) onNotification({ message: 'Reprocessing started', type: 'success' });
                  if (onUpdate) onUpdate({ ...meeting, status: 'processing' });
                } else {
                  const err = await response.json().catch(() => ({}));
                  if (onNotification) onNotification({ message: err.detail || 'Retry failed', type: 'error' });
                }
              } catch {
                if (onNotification) onNotification({ message: 'Retry failed', type: 'error' });
              }
            }}
          >
            <RefreshIcon size={14} /> Reprocess
          </button>
          <button
            className="btn-delete"
            onClick={handleDelete}
            disabled={isDeleting}
          >
            {isDeleting ? 'Deleting...' : <><TrashIcon size={14} /> Delete</>}
          </button>
        </div>
      </div>
    </div>
  );
}

export default MeetingDetail;

