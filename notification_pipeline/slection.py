import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
for p in (PROJECT_ROOT, BASE_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

VENV_PACKAGES = PROJECT_ROOT / ".mindmeshenv" / "Lib" / "site-packages"
if VENV_PACKAGES.exists() and str(VENV_PACKAGES) not in sys.path:
    sys.path.insert(0, str(VENV_PACKAGES))

from typesafe_sdk import TypeSafeClient, Choice
from dotenv import load_dotenv

# chunk_id,
# user_id,
# source,
# category,
# confidence,
# actual_text_in_chunk,
# status,
# is_active,
# chat_name,
# timestamp,
# completed_at,
# next_reminder,
# reminder_count
jev_client=TypeSafeClient()

def categorize(user_query: str):

    response = jev_client.system_one(
        state=user_query,
        questions={
            "query_type": Choice(
                instructions=(
                    "Classify the given message into exactly ONE of "
                    "the five categories below. Understand the actual "
                    "meaning and intention of the message, not just "
                    "individual keywords. Use only information present "
                    "in the message. Do not assume missing details."
                ),
                criteria={
                    "WORK": (
                        "Choose this category for a task, assignment, work "
                        "item, goal, or plan of action without an explicit "
                        "due date. Examples: 'I need to finish the project', "
                        "'Let's build an AI chatbot'. Use DEADLINE when a "
                        "task has an explicit due date. Do not choose this "
                        "category for an event announcement unless it also "
                        "describes a task that needs to be completed."
                    ),

                    "DEADLINE": (
                        "Choose this category for a task, assignment, or "
                        "obligation that must be completed by a stated or "
                        "clearly implied deadline. Examples: 'Submit the "
                        "assignment by Friday', 'Apply before October 20'. "
                        "Do not choose this category for an event that has "
                        "a date but requires no task to be completed."
                    ),

                    "COMMITMENT": (
                        "Choose this category when someone explicitly "
                        "promises, agrees, or commits to doing something "
                        "for themselves or another person. This includes "
                        "promises to perform an action, repay money, "
                        "deliver something, help someone, or fulfill an "
                        "agreement. Examples: 'I will return your money "
                        "tomorrow', 'I promise to send you the notes', "
                        "'I'll help you with the project', 'I agreed to "
                        "pay him back next week'. The message must express "
                        "a commitment or promise, not merely mention a "
                        "possible future action."
                    ),

                    "EVENT": (
                        "Choose this category when the main purpose of "
                        "the message is to announce, invite someone to, "
                        "schedule, or remind someone about a significant "
                        "event. Examples include appointments, meetings, "
                        "interviews, birthdays, wedding anniversaries, "
                        "weddings, hackathons, exams, conferences, and "
                        "scheduled gatherings. Examples: 'The hackathon "
                        "starts on Saturday', 'Your interview is at 10 AM "
                        "tomorrow', 'My birthday is on November 5', "
                        "'Our team meeting is scheduled for Monday'. "
                        "The message may include a date, time, location, "
                        "or invitation. Do not classify an ordinary task "
                        "as an event just because it mentions a date."
                    ),

                    "NORMAL": (
                        "Choose this category when the message does not "
                        "clearly match any of the three categories above. "
                        "This includes ordinary conversations, greetings, "
                        "casual discussions, general information, jokes, "
                        "thank-you messages, routine email notifications, "
                        "advertisements, promotional messages, spam, and "
                        "unwanted marketing emails. Examples: 'How are "
                        "you?', 'Thanks for your help', 'Check out our "
                        "new offers', 'Your newsletter is here'. Do not "
                        "mark a message as important merely because it "
                        "comes from an email or contains a date."
                    )
                },
            )
        },
    )

    return response.answers["query_type"].choice
