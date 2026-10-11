#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================

user_problem_statement: |
  Review Management System for Bong Hneshel food-delivery app. After an order is
  delivered, the customer is texted + emailed a token-gated link (no login) to rate
  the exact dishes they ordered (1-5 stars + optional comment). The delay before the
  link is sent is configurable in Admin -> Settings (default 1 day). Submitted reviews
  land in an admin moderation queue (the customer is NOT told; they see "posted").
  Only admin-approved reviews appear publicly on menu items. Admin can bulk-upload
  historical reviews via CSV (go live immediately).

backend:
  - task: "Reviews backend: token request, submit (moderated), item reviews, summary, ratings on menu"
    implemented: true
    working: true
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "Added db.reviews + db.review_requests, delivery-triggered scheduling (_schedule_review_request on both delivery-partner and admin delivered hooks), background sweep loop, token endpoints GET /reviews/request/{token} + POST /reviews/submit (status=pending), GET /menu-items/{id}/reviews (approved only), GET /reviews/summary. Menu endpoints (_hydrate_menu, /menu/anytime) now carry avg_rating+review_count. Verified via tests/test_reviews_smoke.py: request->submit->pending hidden->admin approve->public visible->summary->CSV bulk upload all PASS."

  - task: "Admin review moderation + CSV bulk upload"
    implemented: true
    working: true
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: true
        agent: "main"
        comment: "GET /admin/reviews?status=, POST /admin/reviews/{id}/moderate (approve|reject), DELETE /admin/reviews/{id}, POST /admin/reviews/bulk-upload (CSV: item_id/item_name,rating,comment,customer_name -> approved, source=admin_bulk). All admin-gated. Smoke test PASS."

  - task: "Settings: reviews_enabled + review_request_delay_days"
    implemented: true
    working: true
    file: "backend/server.py"
    stuck_count: 0
    priority: "medium"
    needs_retesting: true

frontend:
  - task: "Public token-gated review page /review/[token]"
    implemented: true
    working: "NA"
    file: "frontend/app/review/[token].tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: "No-login page: shows dishes with images, 1-5 star selector + optional comment per dish, submit -> success screen ('Thanks! Your review has been posted'). Idempotent/already-submitted shows success. Screenshot smoke test confirms render."

  - task: "Admin Reviews page (moderation queue + CSV bulk upload)"
    implemented: true
    working: "NA"
    file: "frontend/app/admin/reviews.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Pending/Approved/Rejected tabs with counts, approve/reject/delete, CSV bulk upload via expo-document-picker (multipart fetch). Added to AdminShell nav + admin/_layout."

  - task: "Customer menu: rating badge + reviews modal"
    implemented: true
    working: "NA"
    file: "frontend/app/(tabs)/menu.tsx"
    stuck_count: 0
    priority: "medium"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: "A la carte + Always Available rows show a star rating pill + 'See reviews' when review_count>0, opening ReviewsModal that lists approved reviews. src/components/ItemReviews.tsx."

  - task: "Admin Settings: Reviews section (toggle + delay days)"
    implemented: true
    working: "NA"
    file: "frontend/app/admin/settings.tsx"
    stuck_count: 0
    priority: "medium"
    needs_retesting: true

metadata:
  created_by: "main_agent"
  version: "1.8"
  test_sequence: 17
  run_ui: false

test_plan:
  current_focus:
    - "Reviews backend: token request, submit (moderated), item reviews, summary, ratings on menu"
    - "Admin review moderation + CSV bulk upload"
    - "Public token-gated review page /review/[token]"
    - "Admin Reviews page (moderation queue + CSV bulk upload)"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
  - agent: "main"
    message: |
      Implemented the Review Management System (backend + frontend). Please test:
      BACKEND (high priority):
       1. Full review lifecycle: seed a review_request doc (or mark an order delivered
          via POST /api/delivery/orders/{id}/status status=delivered with a delivery
          partner, or admin POST /api/orders/{id}/status status=delivered) -> a
          review_request is created. GET /api/reviews/request/{token} returns items.
          POST /api/reviews/submit {token, reviews:[{item_id,rating,comment}]} ->
          reviews stored as status=pending, customer gets generic success. Re-submit
          is idempotent (still success).
       2. Moderation hides reviews: GET /api/menu-items/{item_id}/reviews must NOT
          include pending reviews. After POST /api/admin/reviews/{id}/moderate
          {action:approve}, the review appears and avg_rating/review_count update.
          reject/delete also work. All /admin/reviews* require admin bearer token
          (401 without).
       3. CSV bulk upload: POST /api/admin/reviews/bulk-upload (multipart file) with
          columns item_id(or item_name),rating,comment,customer_name -> inserted as
          approved; unknown items/invalid ratings reported in errors[].
       4. Menu ratings: GET /api/menu/current items + GET /api/menu/anytime items now
          include avg_rating + review_count.
      Admin creds in /app/memory/test_credentials.md (admin@bong-hneshel.ca).
      Admin login: POST /api/admin/login {email,password} -> token.
      NOTE: Do NOT run end-to-end Stripe checkout (LIVE key in .env). Use existing
      delivered orders or seed review_requests directly for the flow.
      FRONTEND: /review/{token} public page (no login), Admin -> Reviews page
      (moderation + CSV upload), customer Menu tab rating pill + reviews modal,
      Admin -> Settings Reviews section (toggle + delay days).
