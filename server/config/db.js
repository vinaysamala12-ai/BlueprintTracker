const mongoose = require('mongoose');

const connectDB = async (retries = 5, delay = 3000) => {
  for (let attempt = 1; attempt <= retries; attempt++) {
    try {
      const conn = await mongoose.connect(
        process.env.MONGODB_URI || 'mongodb://localhost:27017/approval-workflow',
        { serverSelectionTimeoutMS: 5000 }
      );
      console.log(`✅ MongoDB connected: ${conn.connection.host}`);
      return;
    } catch (error) {
      console.error(`❌ MongoDB connection attempt ${attempt}/${retries} failed: ${error.message}`);
      if (attempt < retries) {
        console.log(`   Retrying in ${delay / 1000}s…`);
        await new Promise(r => setTimeout(r, delay));
      } else {
        console.error('   Could not connect to MongoDB. Start MongoDB or set MONGODB_URI in server/.env');
        console.error('   Server will continue running — API calls will fail until MongoDB is available.');
      }
    }
  }
};

module.exports = connectDB;
