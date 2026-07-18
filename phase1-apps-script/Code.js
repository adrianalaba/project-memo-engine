/**
 * Project Memo Engine - Core Application Logic
 * Architectural Strategy: Decouple sheet read/writes from UI rendering.
 */

// Custom menu hook to launch the engine from the Google Sheets UI
function onOpen() {
  SpreadsheetApp.getUi()
      .createMenu('🧠 Memo Engine')
      .addItem('Launch Quiz Sidebar', 'showSidebar')
      .addToUi();
}

// Render the HTML Sidebar container
function showSidebar() {
  const html = HtmlService.createTemplateFromFile('Sidebar')
      .evaluate()
      .setTitle('Memo Engine: Core Quiz');
  SpreadsheetApp.getUi().showSidebar(html);
}

/**
 * Fetches a random active flashcard from fact_flashcards
 * @return {Object} Card data payload
 */
function getRandomCard() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const cardSheet = ss.getSheetByName('fact_flashcards');
  const data = cardSheet.getDataRange().getValues();
  
  // Parse headers to dynamically find column indices
  const headers = data[0];
  const idxId = headers.indexOf('card_id');
  const idxQuestion = headers.indexOf('question');
  const idxAnswer = headers.indexOf('correct_answer');
  const idxActive = headers.indexOf('is_active');
  
  // Filter for active cards only (skipping header row)
  const activeCards = [];
  for (let i = 1; i < data.length; i++) {
    if (data[i][idxActive] === true || data[i][idxActive] === 'TRUE') {
      activeCards.push({
        card_id: data[i][idxId],
        question: data[i][idxQuestion],
        correct_answer: data[i][idxAnswer]
      });
    }
  }
  
  if (activeCards.length === 0) return null;
  
  // Pick a random card from the filtered array
  const randomIndex = Math.floor(Math.random() * activeCards.length);
  return activeCards[randomIndex];
}

/**
 * Writes a transactional log back to the fact_quiz_logs ledger
 * @param {Object} logData 
 */
function logQuizAttempt(logData) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const logSheet = ss.getSheetByName('fact_quiz_logs');
  
  const timestamp = new Date();
  const logId = 'LOG-' + timestamp.getTime(); // Simple auto-generated unique ID
  
  // Append row matching the exact schema definition
  logSheet.appendRow([
    logId,
    logData.card_id,
    timestamp,
    logData.user_response,
    logData.is_correct,
    logData.response_time_ms
  ]);
  
  return true;
}