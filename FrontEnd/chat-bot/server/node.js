import express from "express";
import pg from "pg";
import bcrypt from "bcrypt";
import cors from "cors";



const app = express();
app.use(cors());
app.use(express.json());


const pool = new pg.Pool({
    user: 'postgres', 
    host: 'localhost',
    database: 'jaff', 
    password: 'root', 
    port: 5432,
});



// Get chat history (guest session)
app.get("/api/chat-history/:sessionId", async (req, res) => {
  try {
    const result = await pool.query(
      "SELECT * FROM chat_history ORDER BY timestamp DESC LIMIT 100"
    );
    res.json({ success: true, history: result.rows });
  } catch (error) {
    console.error(error);
    res.status(500).json({ success: false, error: "Failed to fetch chat history" });
  }
});

// Save chat message (guest session)
app.post("/api/save-chat", async (req, res) => {
  const { message, sender, timestamp } = req.body;

  try {
    const result = await pool.query(
      "INSERT INTO chat_history (message, sender) VALUES ($1, $2) RETURNING *",
      [message, sender]
    );
    res.json({ success: true, chat: result.rows[0] });
  } catch (error) {
    console.error(error);
    res.status(500).json({ success: false, error: "Failed to save chat" });
  }
});

app.listen(5000, () => {
  console.log("Server running on http://localhost:5000");
});