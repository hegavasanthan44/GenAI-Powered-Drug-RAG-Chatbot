import React, { useState, useEffect } from "react";
import ChatBot from "./componenets/chatbot";

const App = () => {
  const [showHistory, setShowHistory] = useState(false);
  const [chatHistory, setChatHistory] = useState([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);

  useEffect(() => {
    fetchChatHistory();
  }, []);

  const fetchChatHistory = async () => {
    setIsLoadingHistory(true);
    try {
      const sessionId = "guest-session";
      const res = await fetch(`http://localhost:5000/api/chat-history/${sessionId}`);
      const data = await res.json();
      if (data.success) {
        setChatHistory(data.history);
      }
    } catch (err) {
      console.error("Failed to fetch chat history:", err);
    } finally {
      setIsLoadingHistory(false);
    }
  };

  const handleSaveChat = () => {
    // Refresh the chat history when a new message is saved
    fetchChatHistory();
  };

  return (
    <div className="h-screen flex bg-gray-50">
      {/* History Sidebar */}
      {showHistory && (
        <div className="w-80 bg-white border-r border-gray-200 p-5 overflow-y-auto shadow-sm">
          <div className="flex justify-between items-center mb-6">
            <h2 className="text-xl font-semibold text-gray-800">Chat History</h2>
            <button 
              onClick={() => setShowHistory(false)}
              className="text-gray-400 hover:text-gray-600 p-1 rounded-full hover:bg-gray-100 transition"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
              </svg>
            </button>
          </div>
          
          {isLoadingHistory ? (
            <div className="flex justify-center py-10">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
            </div>
          ) : chatHistory.length === 0 ? (
            <div className="text-center py-10 text-gray-500">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-12 w-12 mx-auto text-gray-300 mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <p>No chat history yet</p>
            </div>
          ) : (
            <div className="space-y-3">
              {chatHistory.map((chat, index) => (
                <div key={index} className="p-4 bg-gray-50 rounded-lg border border-gray-100 hover:bg-blue-50 transition">
                  <div className="flex items-start justify-between">
                    <p className={`text-sm font-medium ${chat.sender === "user" ? "text-blue-600" : "text-green-600"}`}>
                      {chat.sender === "user" ? "You" : "Bot"}
                    </p>
                    <p className="text-xs text-gray-400">
                      {new Date(chat.timestamp).toLocaleString("en-IN", { 
  timeZone: "Asia/Kolkata" 
})}
                    </p>
                  </div>
                  <p className="text-sm text-gray-700 mt-2">{chat.message}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      
      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col">
        <div className="bg-white border-b border-gray-200 p-4 flex justify-between items-center shadow-sm">
          <div className="flex items-center space-x-4">
            <button
              onClick={() => setShowHistory(!showHistory)}
              className="flex items-center space-x-2 bg-blue-50 text-blue-700 px-4 py-2 rounded-lg hover:bg-blue-100 transition"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M3 5a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 10a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 15a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z" clipRule="evenodd" />
              </svg>
             </button>
            <span className="text-gray-700">Medical RAG ChatBot</span>
          </div>
        </div>
        <ChatBot username="guest" onSaveChat={handleSaveChat} />
      </div>
    </div>
  );
};

export default App;