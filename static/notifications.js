/**
 * Browser Push Notifications for Timmy Time Dashboard
 * 
 * Handles browser Notification API integration for:
 * - Briefing ready notifications
 * - Task completion notifications
 * - Swarm event notifications
 */

(function() {
  'use strict';

  // Notification state
  let notificationsEnabled = false;
  let wsConnection = null;

  /**
   * Request permission for browser notifications
   */
  async function requestNotificationPermission() {
    if (!('Notification' in window)) {
      console.log('Browser notifications not supported');
      return false;
    }

    if (Notification.permission === 'granted') {
      notificationsEnabled = true;
      return true;
    }

    if (Notification.permission === 'denied') {
      console.log('Notification permission denied');
      return false;
    }

    const permission = await Notification.requestPermission();
    notificationsEnabled = permission === 'granted';
    return notificationsEnabled;
  }

  /**
   * Show a browser notification
   */
  function showNotification(title, options = {}) {
    if (!notificationsEnabled || Notification.permission !== 'granted') {
      return;
    }

    const defaultOptions = {
      icon: '/static/favicon.ico',
      badge: '/static/favicon.ico',
      tag: 'timmy-notification',
      requireInteraction: false,
    };

    const notification = new Notification(title, { ...defaultOptions, ...options });

    notification.onclick = () => {
      window.focus();
      notification.close();
    };

    return notification;
  }

  /**
   * Show briefing ready notification
   */
  function notifyBriefingReady(briefingInfo = {}) {
    const approvalCount = briefingInfo.approval_count || 0;
    const body = approvalCount > 0 
      ? `Your morning briefing is ready. ${approvalCount} item(s) await your approval.`
      : 'Your morning briefing is ready.';

    showNotification('Morning Briefing Ready', {
      body,
      tag: 'briefing-ready',
      requireInteraction: true,
    });
  }

  /**
   * Show task completed notification
   */
  function notifyTaskCompleted(taskInfo = {}) {
    const { task_id, agent_name, result } = taskInfo;
    const body = result 
      ? `Task completed by ${agent_name || 'agent'}: ${result.substring(0, 100)}${result.length > 100 ? '...' : ''}`
      : `Task ${task_id?.substring(0, 8)} completed by ${agent_name || 'agent'}`;

    showNotification('Task Completed', {
      body,
      tag: `task-${task_id}`,
    });
  }

  /**
   * Show agent joined notification
   */
  function notifyAgentJoined(agentInfo = {}) {
    const { name, agent_id } = agentInfo;
    showNotification('Agent Joined Swarm', {
      body: `${name || 'New agent'} (${agent_id?.substring(0, 8)}) has joined the swarm.`,
      tag: `agent-joined-${agent_id}`,
    });
  }

  /**
   * Show task assigned notification
   */
  function notifyTaskAssigned(taskInfo = {}) {
    const { task_id, agent_name } = taskInfo;
    showNotification('Task Assigned', {
      body: `Task assigned to ${agent_name || 'agent'}`,
      tag: `task-assigned-${task_id}`,
    });
  }

  /**
   * Connect to WebSocket for real-time notifications
   */
  function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/swarm/live`;

    wsConnection = new WebSocket(wsUrl);

    wsConnection.onopen = () => {
      console.log('WebSocket connected for notifications');
    };

    wsConnection.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        handleWebSocketEvent(data);
      } catch (err) {
        console.error('Failed to parse WebSocket message:', err);
      }
    };

    wsConnection.onclose = () => {
      console.log('WebSocket disconnected, retrying in 5s...');
      setTimeout(connectWebSocket, 5000);
    };

    wsConnection.onerror = (err) => {
      console.error('WebSocket error:', err);
    };
  }

  /**
   * Handle WebSocket events and trigger notifications
   */
  function handleWebSocketEvent(event) {
    if (!notificationsEnabled) return;

    switch (event.event) {
      case 'briefing_ready':
        notifyBriefingReady(event.data);
        break;
      case 'task_completed':
        notifyTaskCompleted(event.data);
        break;
      case 'agent_joined':
        notifyAgentJoined(event.data);
        break;
      case 'task_assigned':
        notifyTaskAssigned(event.data);
        break;
      default:
        // Unknown event type, ignore
        break;
    }
  }

  /**
   * Initialize notifications system
   */
  async function init() {
    // Request permission on user interaction
    const enableBtn = document.getElementById('enable-notifications');
    if (enableBtn) {
      enableBtn.addEventListener('click', async () => {
        const granted = await requestNotificationPermission();
        if (granted) {
          enableBtn.textContent = 'Notifications Enabled';
          enableBtn.disabled = true;
          connectWebSocket();
        }
      });
    }

    // Auto-request if permission was previously granted
    if (Notification.permission === 'granted') {
      notificationsEnabled = true;
      connectWebSocket();
    }

    // Listen for briefing ready events via custom event
    document.addEventListener('briefing-ready', (e) => {
      notifyBriefingReady(e.detail);
    });

    // Listen for task completion events
    document.addEventListener('task-completed', (e) => {
      notifyTaskCompleted(e.detail);
    });
  }

  // Expose public API
  window.TimmyNotifications = {
    requestPermission: requestNotificationPermission,
    show: showNotification,
    notifyBriefingReady,
    notifyTaskCompleted,
    notifyAgentJoined,
    notifyTaskAssigned,
    isEnabled: () => notificationsEnabled,
  };

  // Initialize on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
