const mongoose = require('mongoose');

const configSchema = new mongoose.Schema({
  ms365: {
    tenantId:     { type: String, default: '' },
    clientId:     { type: String, default: '' },
    clientSecret: { type: String, default: '' },
    fromEmail:    { type: String, default: '' },
    fromName:     { type: String, default: 'Document Approval System' }
  },
  scheduler: {
    enabled:              { type: Boolean, default: true },
    cronExpression:       { type: String,  default: '0 * * * *' },
    reminderIntervalHours:{ type: Number,  default: 24 },
    maxReminders:         { type: Number,  default: 3 }
  },
  storage: {
    type:         { type: String, enum: ['sharepoint', 'onedrive'], default: 'onedrive' },
    tenantId:     { type: String, default: '' },
    clientId:     { type: String, default: '' },
    clientSecret: { type: String, default: '' },
    driveId:      { type: String, default: '' },
    siteUrl:      { type: String, default: '' },
    folderPath:   { type: String, default: '/' }
  },
  appUrl: { type: String, default: 'http://localhost:3000' }
}, { timestamps: true });

module.exports = mongoose.model('Config', configSchema);
