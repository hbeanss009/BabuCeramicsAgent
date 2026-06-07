"""Manual integration tests for conversation_store (requires Supabase conversations table)."""

from conversation_store import (
    create_conversation,
    generate_thread_id,
    get_conversation,
    update_messages,
)


def run_tests() -> None:
    print("--- Test 1: generate thread_id ---")
    thread_id = generate_thread_id()
    print(f"Generated: {thread_id}")
    assert len(thread_id) == 36

    print("\n--- Test 2: create conversation ---")
    success = create_conversation(
        thread_id=thread_id,
        email="test@example.com",
        name="Jane",
        initial_query="Do you have gold rings?",
        messages=[{"role": "user", "content": "Do you have gold rings?"}],
    )
    print(f"Created: {success}")
    assert success

    print("\n--- Test 3: fetch conversation ---")
    convo = get_conversation(thread_id)
    print(f"Fetched: {convo}")
    assert convo is not None
    assert convo["email"] == "test@example.com"
    assert len(convo["messages"]) == 1

    print("\n--- Test 4: update messages ---")
    new_messages = [
        {"role": "user", "content": "Do you have gold rings?"},
        {"role": "assistant", "content": "Yes we do!"},
        {"role": "user", "content": "What sizes?"},
    ]
    success = update_messages(thread_id, new_messages)
    print(f"Updated: {success}")
    assert success

    convo = get_conversation(thread_id)
    assert convo is not None
    assert len(convo["messages"]) == 3
    print(f"Final message count: {len(convo['messages'])}")

    print("\n--- All tests passed ---")
    print(f"Check Supabase — row with thread_id {thread_id} should exist")


if __name__ == "__main__":
    run_tests()
