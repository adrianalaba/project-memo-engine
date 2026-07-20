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
 * Retrieves a random flashcard that is currently due or overdue for review.
 * @return {Object|null} A flashcard data object, or null if the queue is completely clear.
 */
function getRandomCard() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const cardSheet = ss.getSheetByName('fact_flashcards');
  const data = cardSheet.getDataRange().getValues();
  
  if (data.length <= 1) return null; // Sheet is empty except for headers
  
  const headers = data[0];
  const cardRows = data.slice(1);
  
  const idIdx = headers.indexOf('card_id');
  const subjectIdx = headers.indexOf('subject_id');
  const frontIdx = headers.indexOf('front');
  const backIdx = headers.indexOf('back');
  const repIdx = headers.indexOf('repetition_count');
  const efIdx = headers.indexOf('easiness_factor');
  const dateIdx = headers.indexOf('next_review_date');
  
  const now = new Date();
  // Set timestamp to midnight for a strict date-only calendar comparison
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  
  // Filter out cards whose review date is scheduled in the future
  const dueQueue = cardRows.filter(row => {
    const reviewDateVal = row[dateIdx];
    if (!reviewDateVal) return true; // Treat unassigned dates as due immediately
    
    const reviewDate = new Date(reviewDateVal);
    const reviewDateTime = new Date(reviewDate.getFullYear(), reviewDate.getMonth(), reviewDate.getDate()).getTime();
    
    return reviewDateTime <= today;
  });
  
  if (dueQueue.length === 0) {
    Logger.log("Review queue is clear! No cards are due today.");
    return null;
  }
  
  // Randomly select an item from the verified due array
  const randomIndex = Math.floor(Math.random() * dueQueue.length);
  const selectedCard = dueQueue[randomIndex];
  
  // Return a structural entity map for frontend consumption
  return {
    card_id: selectedCard[idIdx],
    subject_id: selectedCard[subjectIdx],
    front: selectedCard[frontIdx],
    back: selectedCard[backIdx],
    repetition_count: selectedCard[repIdx],
    easiness_factor: selectedCard[efIdx],
    next_review_date: selectedCard[dateIdx],
    // Calculated helper to track back to its physical row index for subsequent updates
    sourceRowIndex: cardRows.indexOf(selectedCard) + 2 
  };
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

function migrateFlashcardSchema() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName('fact_flashcards');
  const lastRow = sheet.getLastRow();
  const lastColumn = sheet.getLastColumn();
  
  // 1. Add headers if they don't exist
  sheet.getRange(1, 5, 1, 3).setValues([['repetition_count', 'easiness_factor', 'next_review_date']]);
  
  if (lastRow > 1) {
    const todayStr = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), "yyyy-MM-dd");
    const rowsToUpdate = lastRow - 1;
    
    // 2. Build initialization vectors
    const repVectors = Array(rowsToUpdate).fill([0]);
    const efVectors = Array(rowsToUpdate).fill([2.5]);
    const dateVectors = Array(rowsToUpdate).fill([todayStr]);
    
    // 3. Batch write backends to minimize API latency
    sheet.getRange(2, 5, rowsToUpdate, 1).setValues(repVectors);
    sheet.getRange(2, 6, rowsToUpdate, 1).setValues(efVectors);
    sheet.getRange(2, 7, rowsToUpdate, 1).setValues(dateVectors);
  }
  Logger.log("Schema migration to Phase 2 completed successfully.");
}

/**
 * Calculates the next state of a flashcard using the SM-2 algorithm.
 * @param {boolean} isPass - User performance boolean from fact_quiz_logs.
 * @param {number} currentRep - Current repetition count.
 * @param {number} currentEf - Current easiness factor.
 * @param {number} previousInterval - The last interval used for scheduling.
 * @return {Object} The calculated metrics for updates {nextRep, nextEf, intervalDays}.
 */
function calculateSM2(isPass, currentRep, currentEf, previousInterval) {
  const q = isPass ? 4 : 1;
  let nextRep = currentRep;
  let nextEf = currentEf;
  let intervalDays = 1;

  if (q < 3) {
    // Incorrect answer: reset the review iteration sequence
    nextRep = 0;
    intervalDays = 1;
    // Adjust EF based on failure response
    nextEf = currentEf + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02));
  } else {
    // Correct answer: advance sequence step
    if (nextRep === 0) {
      intervalDays = 1;
    } else if (nextRep === 1) {
      intervalDays = 6;
    } else {
      intervalDays = Math.round(previousInterval * currentEf);
    }
    nextRep += 1;
    // Adjust EF based on success response
    nextEf = currentEf + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02));
  }

  // Safety guardrail for EF lower bound
  if (nextEf < 1.3) nextEf = 1.3;

  return {
    nextRep: nextRep,
    nextEf: parseFloat(nextEf.toFixed(2)),
    intervalDays: intervalDays
  };
}