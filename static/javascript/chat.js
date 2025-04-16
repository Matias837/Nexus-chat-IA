document.addEventListener('DOMContentLoaded', function() {
    // DOM Elements
    const messageForm = document.getElementById('message-form');
    const messageInput = document.getElementById('message-input');
    const messagesContainer = document.getElementById('chat-messages');
    const typingIndicator = document.getElementById('typing-indicator');
    const newChatBtn = document.getElementById('new-chat-btn');
    
    // Event listener for new chat button
    if (newChatBtn) {
        newChatBtn.addEventListener('click', function() {
            fetch('/conversation/new', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            })
            .then(response => {
                if (response.redirected) {
                    window.location.href = response.url;
                }
            })
            .catch(error => console.error('Error creating new conversation:', error));
        });
    }
    
    // Event listener for delete conversation buttons
    const deleteButtons = document.querySelectorAll('.delete-conversation');
    deleteButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            
            const conversationId = this.getAttribute('data-id');
            if (confirm('Are you sure you want to delete this conversation?')) {
                fetch(`/api/conversations/delete/${conversationId}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    }
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        // Remove the conversation from the sidebar
                        const conversationItem = document.querySelector(`.conversation-item[data-id="${conversationId}"]`);
                        if (conversationItem) {
                            conversationItem.remove();
                        }
                        
                        // Redirect to home if we deleted the current conversation
                        const currentConversationId = messageForm ? messageForm.getAttribute('data-conversation-id') : null;
                        if (currentConversationId === conversationId) {
                            window.location.href = '/';
                        }
                    }
                })
                .catch(error => console.error('Error deleting conversation:', error));
            }
        });
    });
    
    // Chat form submission
    if (messageForm) {
        messageForm.addEventListener('submit', function(e) {
            e.preventDefault();
            
            const message = messageInput.value.trim();
            if (!message) return;
            
            const conversationId = this.getAttribute('data-conversation-id');
            
            // Add user message to the UI immediately
            appendMessage(message, true);
            
            // Clear input field and reset height
            messageInput.value = '';
            messageInput.style.height = 'auto';
            
            // Show typing indicator
            typingIndicator.classList.remove('hidden');
            
            // Scroll to bottom
            scrollToBottom();
            
            // Send message to the server
            fetch('/api/send_message', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    message: message,
                    conversation_id: conversationId
                })
            })
            .then(response => response.json())
            .then(data => {
                // If this is a new conversation, update the form with the new ID
                if (!conversationId && data.conversation_id) {
                    messageForm.setAttribute('data-conversation-id', data.conversation_id);
                    // Update URL without refreshing
                    window.history.pushState({}, '', `/conversation/${data.conversation_id}`);
                }
                
                // Start listening for the streaming response
                startStreaming(data.conversation_id);
            })
            .catch(error => {
                console.error('Error sending message:', error);
                typingIndicator.classList.add('hidden');
                appendErrorMessage("Failed to send message. Please try again.");
            });
        });
    }
    
    // Function to start streaming the response
    function startStreaming(conversationId) {
        const eventSource = new EventSource(`/api/stream_response/${conversationId}`);
        let aiMessageElement = null;
        let aiMessageContent = "";
        
        // Event listener for SSE messages
        eventSource.onmessage = function(event) {
            const data = JSON.parse(event.data);
            
            // Hide typing indicator when streaming begins
            if (!aiMessageElement) {
                typingIndicator.classList.add('hidden');
            }
            
            // Check if it's a completion signal
            if (data.done) {
                eventSource.close();
                return;
            }
            
            // Check for errors
            if (data.error) {
                console.error('Error in stream:', data.error);
                appendErrorMessage(data.error);
                eventSource.close();
                return;
            }
            
            // If this is the first chunk, create the message element
            if (!aiMessageElement) {
                aiMessageElement = createMessageElement("", false, data.messageId);
                messagesContainer.appendChild(aiMessageElement);
                scrollToBottom();
            }
            
            // Append the new text chunk
            if (data.text) {
                aiMessageContent += data.text;
                updateMessageContent(aiMessageElement, aiMessageContent);
                scrollToBottom();
            }
        };
        
        // Error handler
        eventSource.onerror = function(error) {
            console.error('EventSource error:', error);
            typingIndicator.classList.add('hidden');
            appendErrorMessage("Connection error. Please try again.");
            eventSource.close();
        };
    }
    
    // Function to append a user or AI message
    function appendMessage(text, isUser) {
        const messageElement = createMessageElement(text, isUser);
        messagesContainer.appendChild(messageElement);
        scrollToBottom();
    }
    
    // Function to append an error message
    function appendErrorMessage(errorText) {
        const errorElement = document.createElement('div');
        errorElement.classList.add('message', 'error-message');
        errorElement.innerHTML = `
            <div class="message-content">
                <div class="message-text">
                    <i class="fas fa-exclamation-triangle"></i> ${errorText}
                </div>
            </div>
        `;
        messagesContainer.appendChild(errorElement);
        scrollToBottom();
    }
    
    // Function to create a message element
    function createMessageElement(text, isUser, messageId = null) {
        const messageElement = document.createElement('div');
        messageElement.classList.add('message');
        messageElement.classList.add(isUser ? 'user-message' : 'ai-message');
        
        if (messageId) {
            messageElement.setAttribute('data-message-id', messageId);
        }
        
        const now = new Date();
        const timeString = now.getHours().toString().padStart(2, '0') + ':' + 
                          now.getMinutes().toString().padStart(2, '0');
        
        messageElement.innerHTML = `
            <div class="message-avatar">
                <i class="fas ${isUser ? 'fa-user' : 'fa-robot'}"></i>
            </div>
            <div class="message-content">
                <div class="message-text">${text}</div>
                <div class="message-time">${timeString}</div>
            </div>
        `;
        
        return messageElement;
    }
    
    // Function to update message content (for streaming)
    function updateMessageContent(messageElement, newText) {
        const textElement = messageElement.querySelector('.message-text');
        if (textElement) {
            textElement.innerHTML = formatMessageText(newText);
        }
    }
    
    // Function to format message text (convert Markdown, etc.)
    function formatMessageText(text) {
        // Simple code block formatting
        text = text.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
        
        // Simple bold formatting
        text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        
        // Simple italic formatting
        text = text.replace(/\*(.*?)\*/g, '<em>$1</em>');
        
        // Simple link formatting
        text = text.replace(/\[(.*?)\]\((.*?)\)/g, '<a href="$2" target="_blank">$1</a>');
        
        // Preserve line breaks
        text = text.replace(/\n/g, '<br>');
        
        return text;
    }
    
    // Function to scroll chat to bottom
    function scrollToBottom() {
        if (messagesContainer) {
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
    }
    
    // Initial scroll to bottom when page loads
    if (messagesContainer && messagesContainer.scrollHeight > 0) {
        scrollToBottom();
    }
});
