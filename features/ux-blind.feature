Feature: The UX blind probe compares design passes for UI/UX work and applies the pre-registered ux-design rules

  evals/probes/ux_blind.py runs a designer (fable-5-2@high or opus-5-5@xhigh) or no design pass, a sonnet-5-5@medium
  builder and two checklist judges through evalkit, then writes one offline blind file for the owner and applies
  rules UQ, UB and UD of section 4 of evals/results/PREREGISTERED-2026-11-13-think-first.md to the owner's answers.
  Every test uses the stub claude and temp directories.

  # Backed by: tests/test_ux_blind.py::test_plan_counts_36_designs_48_builds_and_48_checklist_calls_for_four_briefs
  Scenario: Plan counts every missing call for four briefs without calling a model
    Given four briefs and an empty root, with a per-run cap of $1
    When plan --json runs
    Then designs_missing is 36, builds_missing is 48, checklist_missing is 48, calls_missing is 132, cost_bound_usd is 132.0 and the stub claude was never started

  # Backed by: tests/test_ux_blind.py::test_plan_text_names_the_counts_and_the_cost_bound
  Scenario: Plan prints the counts and the cost bound as text
    Given four briefs and an empty root
    When plan runs
    Then it prints "designs: 36 missing of 36", "builds: 48 missing of 48", "checklist calls: 48 missing of 48" and "cost bound: $132.00"

  # Backed by: tests/test_ux_blind.py::test_plan_counts_only_what_is_still_missing
  Scenario: Plan counts only what is still missing
    Given one design file ux-01-F-1, all 48 pages but the first D page, and one judge answer
    When plan --json runs
    Then designs_missing is 35, builds_missing is 1 and checklist_missing is 47

  # Backed by: tests/test_ux_blind.py::test_plan_works_while_another_writer_holds_the_lock
  Scenario: Plan takes no lock
    Given another process holds evalkit's exclusive lock
    When plan runs
    Then the exit code is 0

  # Backed by: tests/test_ux_blind.py::test_briefs_need_exactly_eight_checklist_items
  Scenario: A brief whose checklist has 7 items is refused
    Given brief ux-01 with a 7-item checklist.json
    When plan runs
    Then the exit code is 2 and stderr says "exactly 8 items"

  # Backed by: tests/test_ux_blind.py::test_brief_viewport_must_look_like_390x780
  Scenario: A brief whose viewport is not WxH is refused
    Given brief ux-01 with viewport "phone"
    When plan runs
    Then the exit code is 2 and stderr mentions "viewport"

  # Backed by: tests/test_ux_blind.py::test_an_unknown_briefs_directory_is_a_clear_error
  Scenario: A missing briefs directory is a clear error
    Given no briefs directory under the root
    When plan runs
    Then the exit code is 2 and stderr says "no briefs directory"

  # Backed by: tests/test_ux_blind.py::test_the_script_runs_as_a_command_and_defaults_the_root_to_private_ux
  Scenario: The root defaults to private/ux under the evals directory
    Given AGENTING_EVALS_DIR pointing at a temp evals directory holding private/ux/briefs with four briefs
    When the script runs with plan --json and no --root
    Then it exits 0 and designs_missing is 36

  # Backed by: tests/test_ux_blind.py::test_designer_prompt_is_byte_identical_for_fable_and_opus
  Scenario: The designer prompt is the same text for fable-5-2@high and opus-5-5@xhigh
    Given one brief and the design step run for 6 F samples and 3 O samples
    When the logged prompts are compared
    Then all 9 designer prompts are byte-identical, hold the brief description and the six section names, and end with the marker instruction naming ===ANSWER=== and ===END===

  # Backed by: tests/test_ux_blind.py::test_builder_prompt_differs_between_arms_only_in_the_design_paragraph
  Scenario: The builder prompt differs between arms only in the design paragraph
    Given the same description and viewport 390x780 with a design text, another design text and no design
    When the three builder prompts are built
    Then removing the design paragraph leaves identical text; the F and O paragraphs start "A designer wrote this design brief. Follow it:" and the D paragraph is "There is no design brief. Make the design choices yourself."

  # Backed by: tests/test_ux_blind.py::test_each_builder_gets_the_design_of_its_own_arm_and_none_for_d
  Scenario: Each builder receives the design of its own arm
    Given one brief with designs and the build step run
    When the 12 logged builder prompts are inspected
    Then 6 carry the fable designer's text, 3 the opus designer's text and 3 say there is no design brief

  # Backed by: tests/test_ux_blind.py::test_every_model_call_is_restricted_with_the_harness_tools_and_system_prompts
  Scenario: Every call is restricted with the harness tool list and system prompts
    Given one brief taken through design, build and checklist
    When the logged command lines are inspected
    Then all calls carry --restricted; design and build use --tools "Read,Grep,Glob" with the runner system prompt; checklist calls use --tools "" with the judge system prompt

  # Backed by: tests/test_ux_blind.py::test_every_call_runs_in_a_fresh_directory_holding_a_copy_of_the_material
  Scenario: Every call runs in a fresh directory with a copy of the material
    Given one brief with material/conventions.md and the design step run
    When the 9 logged working directories are inspected
    Then each is distinct, lies under <root>/work, holds only conventions.md, is deleted afterwards, and nothing is created under <evals>/private

  # Backed by: tests/test_ux_blind.py::test_checklist_prompt_holds_the_description_the_eight_items_and_the_page_source
  Scenario: The checklist prompt holds the description, the 8 items and the page source
    Given description "Add a shop.", items K1 to K8 and the page source "<html>PAGE-SOURCE</html>"
    When the checklist prompt is built
    Then it contains all three and each line reads "K3: Is 3 true? (answer true when: 3 holds)"

  # Backed by: tests/test_ux_blind.py::test_comments_are_removed
  Scenario: HTML comments are removed from a built page
    Given a page with "<!-- F arm -->" in head and a multi-line comment in body
    When it is sanitised
    Then no <!-- remains and the doctype is kept

  # Backed by: tests/test_ux_blind.py::test_title_is_forced_to_prototype
  Scenario: The title becomes Prototype
    Given a page titled "Fable design pass"
    When it is sanitised
    Then the title reads "Prototype" and "Fable" appears nowhere

  # Backed by: tests/test_ux_blind.py::test_a_missing_title_is_added
  Scenario: A page without a title gets one
    Given a page with no <title>
    When it is sanitised
    Then exactly one "<title>Prototype</title>" is present

  # Backed by: tests/test_ux_blind.py::test_an_svg_title_in_the_body_is_left_alone
  Scenario: Only the document title is replaced
    Given a head title "Head" and an svg <title>Star</title> in the body
    When it is sanitised
    Then the head title is "Prototype" and the svg title is still "Star"

  # Backed by: tests/test_ux_blind.py::test_generator_meta_is_removed_in_either_attribute_order
  Scenario: The generator meta is removed
    Given metas name="generator" and content="x" name='Generator' next to a viewport meta
    When it is sanitised
    Then both generator metas are gone and the viewport meta stays

  # Backed by: tests/test_ux_blind.py::test_the_csp_is_the_first_child_of_head
  Scenario: A Content-Security-Policy meta becomes the first child of head
    Given a page with <head lang="tr"><meta charset="utf-8">
    When it is sanitised
    Then the head opens with the meta http-equiv Content-Security-Policy whose content is default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; font-src data:, once

  # Backed by: tests/test_ux_blind.py::test_a_head_is_created_when_the_page_has_none
  Scenario: A head is created when the page has none
    Given <html><body>x</body></html>
    When it is sanitised
    Then the page is <html><head> the CSP meta and <title>Prototype</title> </head><body>

  # Backed by: tests/test_ux_blind.py::test_external_links_scripts_and_imports_are_removed
  Scenario: External links, scripts and imports are removed
    Given a stylesheet link to https://fonts.example, a preload link to //cdn.example, scripts with src http:// and //, and two @import rules, next to a data: icon link and an inline script
    When it is sanitised
    Then the external ones are gone and the page is valid; the data: icon link, the inline script and the other CSS stay

  # Backed by: tests/test_ux_blind.py::test_a_remaining_external_url_in_src_href_or_action_is_invalid
  Scenario: An external URL in src, href or action makes the page invalid
    Given img src="https://x.example/a.png", a href='http://x.example', form action="//x.example/post", an iframe src and img.src assigned in a script
    When each is sanitised
    Then each page is invalid with the reason about src, href or action

  # Backed by: tests/test_ux_blind.py::test_a_remaining_external_url_in_css_url_is_invalid
  Scenario: An external URL in CSS url() makes the page invalid
    Given background:url(https://x.example/a.png) and URL( '//x.example/a.png' )
    When each is sanitised
    Then each page is invalid with a url() reason

  # Backed by: tests/test_ux_blind.py::test_a_script_that_reaches_an_external_url_is_invalid
  Scenario: A script reaching an external URL makes the page invalid
    Given fetch("https://x.example/api"), fetch('//x.example/api'), XMLHttpRequest open("GET", "http://x.example/a"), import("https://x.example/m.js") and new WebSocket("wss://x.example/s")
    When each is sanitised
    Then each page is invalid

  # Backed by: tests/test_ux_blind.py::test_xmlns_and_plain_text_mentions_are_fine
  Scenario: An xmlns URL and plain-text mentions are fine
    Given an svg with xmlns="http://www.w3.org/2000/svg", text "https://example.com/rules", a JS line comment with http:// and the word XMLHttpRequest in a comment
    When it is sanitised
    Then the page is valid and keeps the xmlns

  # Backed by: tests/test_ux_blind.py::test_a_document_with_neither_html_nor_body_is_invalid
  Scenario: Text with neither <html nor <body is invalid
    Given the text "Sorry, I cannot build that."
    When it is sanitised
    Then the page is invalid with "no <html or <body"

  # Backed by: tests/test_ux_blind.py::test_a_body_without_an_html_tag_is_accepted
  Scenario: A body without an html tag is accepted
    Given <body>x</body>
    When it is sanitised
    Then the page is valid and gets a head

  # Backed by: tests/test_ux_blind.py::test_the_size_limit_is_300_kb_of_utf8_bytes
  Scenario: The size limit is 300 KB of UTF-8 bytes
    Given a page of exactly 307200 bytes, one of 307201 bytes and one of 307202 bytes made of 2-byte characters
    When each is sanitised
    Then the first is valid and the others are invalid with "larger than 300 KB"

  # Backed by: tests/test_ux_blind.py::test_a_wrapping_code_fence_is_stripped
  Scenario: A wrapping code fence is stripped from the answer
    Given an answer "```html ... ```"
    When the fence is stripped
    Then only the HTML remains

  # Backed by: tests/test_ux_blind.py::test_design_stores_text_usage_cost_observed_model_and_attempts
  Scenario: A design is stored with its text, usage, cost, observed model and attempts
    Given one brief and the design step run
    When designs/ux-01-F-2.json is read
    Then it holds the design text, cell "fable-5-2@high", model_observed "claude-test-fable-5-2", attempts 1, cost_usd 0.01, thinking_tokens 100 and slot_failed false; 9 design files exist

  # Backed by: tests/test_ux_blind.py::test_a_missing_answer_block_is_a_failed_design_retried_twice
  Scenario: A design with no answer block is retried twice and then left missing
    Given a model that never prints the marker lines and one brief
    When the design step runs
    Then 27 calls are made (3 for each of 9 slots), no design file exists, every attempt is logged with reason no_answer_block and plan still reports 9 designs missing

  # Backed by: tests/test_ux_blind.py::test_the_attempt_limit_holds_across_invocations
  Scenario: The attempt limit holds across invocations
    Given 9 slots with 3 failed attempts each in attempts.jsonl
    When the design step runs again
    Then no further call is made and plan reports 9 designs out of attempts

  # Backed by: tests/test_ux_blind.py::test_a_wrong_model_attempt_is_invalid_and_retried
  Scenario: A wrong-model attempt is invalid and retried
    Given the fable designer answers as claude-test-fable-5-2-next on its first call
    When the design step runs
    Then the first attempt is logged as not accepted with a model_mismatch reason, the second is accepted, and the design records attempts 2

  # Backed by: tests/test_ux_blind.py::test_a_refused_attempt_is_invalid_and_retried
  Scenario: A refused attempt is invalid and retried
    Given the opus designer ends its first call with stop_reason "refusal"
    When the design step runs
    Then the first attempt is logged with reason "refused" and the design records attempts 2

  # Backed by: tests/test_ux_blind.py::test_a_fable_slot_with_a_wrong_model_or_refused_attempt_is_flagged_failed
  Scenario: A Fable slot with a refused or wrong-model attempt is flagged failed
    Given the fable designer answers as another model, or refuses, on its first call
    When the design step runs
    Then that design has slot_failed true, the next one has slot_failed false and plan reports fable_flagged_slots 1

  # Backed by: tests/test_ux_blind.py::test_an_opus_slot_with_a_wrong_model_attempt_is_not_flagged
  Scenario: An Opus slot with a wrong-model attempt is not flagged
    Given the opus designer answers as another model on its first call
    When the design step runs
    Then the design records attempts 2 and slot_failed false

  # Backed by: tests/test_ux_blind.py::test_the_budget_stops_the_run
  Scenario: The budget stops the run
    Given four briefs, $0.01 per call and --max-usd 0.025 with one job
    When the design step runs
    Then exactly 3 calls are made, 3 design files exist and it prints "design cost $0.0300"

  # Backed by: tests/test_ux_blind.py::test_run_commands_hold_the_evalkit_lock_and_refuse_when_it_is_taken
  Scenario: Design, build and checklist take evalkit's lock
    Given another process holds evalkit's exclusive lock
    When design, build or checklist runs
    Then the exit code is 2, stderr says "already writing" and no model is called

  # Backed by: tests/test_ux_blind.py::test_a_missing_cell_stops_before_any_call
  Scenario: A missing cell stops the run before any call
    Given cells.json without fable-5-2@high
    When design runs
    Then the exit code is 2, stderr names fable-5-2@high and no model is called

  # Backed by: tests/test_ux_blind.py::test_build_stores_pages_under_random_hex_ids_with_a_private_mapping
  Scenario: Built pages get random 8-hex ids and a private mapping
    Given one brief with designs and the build step run
    When pages/ and pages.json are read
    Then 12 pages exist under ids matching [0-9a-f]{8}, and pages.json maps them to F 1-6 (blocks 1,1,1,2,2,2), O 1-3 (block 1) and D 1-3 (block 2) of ux-01

  # Backed by: tests/test_ux_blind.py::test_page_ids_file_names_and_contents_do_not_reveal_the_arm
  Scenario: Page file names and contents do not reveal the arm
    Given a builder that answers with a page titled Fable, with a generator meta and an F-arm comment
    When the build step runs
    Then the 12 stored files are named <8 hex>.html, contain no "fable", "generator" or comment, read "Prototype" as title and carry the CSP

  # Backed by: tests/test_ux_blind.py::test_a_design_is_needed_before_its_page_can_be_built
  Scenario: An F or O page waits for its design
    Given one brief with no designs
    When the build step runs
    Then only the 3 D pages are built and plan reports 9 builds waiting for a design

  # Backed by: tests/test_ux_blind.py::test_an_invalid_page_is_rebuilt_twice_then_left_missing
  Scenario: An invalid page is rebuilt twice and then left missing
    Given a builder that always answers with img src="https://x.example/a.png"
    When the build step runs
    Then 36 builder calls are made (3 for each of 12 slots), no page is stored and every attempt is logged with a page_invalid reason

  # Backed by: tests/test_ux_blind.py::test_a_page_with_no_answer_block_is_retried_and_stored_on_a_later_run
  Scenario: A build with no answer block is stored on a later run
    Given a builder that omits the marker lines, then a good builder after attempts.jsonl is cleared
    When the build step runs twice
    Then the first run stores nothing and the second stores 12 pages

  # Backed by: tests/test_ux_blind.py::test_a_fenced_answer_is_unwrapped_before_it_is_stored
  Scenario: A fenced HTML answer is unwrapped before it is stored
    Given a builder that wraps its page in ```html fences
    When the build step runs
    Then no stored page contains ``` and each keeps its body

  # Backed by: tests/test_ux_blind.py::test_the_build_attempt_log_names_the_slot_and_the_cell
  Scenario: The build attempt log names the slot and the cell
    Given one brief built
    When attempts.jsonl is read
    Then the entry for slot "build|ux-01|F|1" has cell sonnet-5-5@medium, model_observed claude-test-sonnet-5-5 and accepted true

  # Backed by: tests/test_ux_blind.py::test_each_judge_reads_each_block_one_page_once
  Scenario: Each judge reads each block-1 page once
    Given one brief with 12 built pages
    When the checklist step runs
    Then 12 calls are made (6 pages x 2 judges), checklist.json holds the 6 block-1 pages with both judges' answers and score 1.0, and plan reports 0 checklist calls missing

  # Backed by: tests/test_ux_blind.py::test_the_judge_prompt_holds_the_page_source_of_the_page_it_judges
  Scenario: The judge prompt holds the page source
    Given one brief with 12 built pages
    When the first checklist prompt is read
    Then it contains the source of exactly one stored page

  # Backed by: tests/test_ux_blind.py::test_an_item_is_credited_only_when_both_judges_say_true
  Scenario: An item is credited only when both judges say true
    Given judge A false on K3 and judge B false on K5, all other items true
    When the credited items are computed
    Then they are K1, K2, K4, K6, K7, K8; with only one judge present the result is none

  # Backed by: tests/test_ux_blind.py::test_stored_page_results_credit_what_both_judges_said_true
  Scenario: The stored page result credits what both judges said true
    Given the fable judge false on K2 and the opus judge false on K4
    When the checklist step runs
    Then each page entry credits K1, K3, K5, K6, K7, K8 and scores 0.75

  # Backed by: tests/test_ux_blind.py::test_an_unparseable_judge_reply_is_retried_up_to_twice_then_left_missing
  Scenario: An unparseable judge reply is retried twice and then left missing
    Given judges that never answer with the JSON object
    When the checklist step runs
    Then 36 calls are made, nothing is stored and plan reports 12 checklist calls missing

  # Backed by: tests/test_ux_blind.py::test_a_judge_reply_that_is_fixed_on_the_retry_is_stored
  Scenario: A judge reply that is fixed on the third attempt is stored
    Given the first 2 judge replies are unparseable
    When the checklist step runs
    Then 14 calls are made and plan reports 0 checklist calls missing

  # Backed by: tests/test_ux_blind.py::test_a_reply_without_all_eight_real_booleans_is_not_accepted
  Scenario: A reply without K1 to K8 as true or false is not accepted
    Given replies with 7 keys, an extra K9, "yes" for K8, 1 for K8 or a list
    When they are parsed
    Then none is accepted and the complete reply is

  # Backed by: tests/test_ux_blind.py::test_a_wrong_model_judge_is_invalid_and_retried
  Scenario: A wrong-model judge attempt is invalid and retried
    Given the fable judge answers as another model on its first call
    When the checklist step runs
    Then one attempt is logged as not accepted with a model_mismatch reason and no checklist call stays missing

  # Backed by: tests/test_ux_blind.py::test_the_pair_table_has_24_pairs_12_per_block_and_no_page_twice
  Scenario: The pair table has 24 pairs, 12 per block, and no page twice
    Given 48 built pages for four briefs
    When page runs
    Then pairs.json has 24 pairs with positions 1 to 24, 12 in block 1 and 12 in block 2, 24 distinct 10-hex pair ids, and its 48 page references are exactly the 48 built pages

  # Backed by: tests/test_ux_blind.py::test_block_one_pairs_f_against_o_and_block_two_uses_f_samples_4_to_6_against_d
  Scenario: Block 1 pairs F against O and block 2 pairs F samples 4-6 against D
    Given 48 built pages for four briefs
    When page runs
    Then each block-1 pair holds F sample s against O sample s (s in 1-3), each block-2 pair holds F sample s+3 against D sample s, and each brief has 3 pairs per block

  # Backed by: tests/test_ux_blind.py::test_one_shuffled_order_with_a_random_side_per_pair
  Scenario: The 24 pairs are shuffled in one order with a random side each
    Given seed 12345
    When page runs
    Then the order is not the construction order, blocks and briefs are mixed, and F is on the left in between 4 and 20 pairs

  # Backed by: tests/test_ux_blind.py::test_the_pair_table_is_a_function_of_the_stored_seed
  Scenario: The pair table is a function of the stored seed
    Given seed 777 twice and seed 778
    When the table is made
    Then seed 777 gives the same table twice, with seed 777 stored, and seed 778 gives different pairs

  # Backed by: tests/test_ux_blind.py::test_pairs_are_not_reshuffled_when_pairs_json_exists
  Scenario: Pairs are not reshuffled when pairs.json exists
    Given pairs.json made with seed 1
    When page runs again with seed 2 available
    Then pairs.json and blind.html are byte-identical to before

  # Backed by: tests/test_ux_blind.py::test_page_refuses_while_pages_are_not_built
  Scenario: Page refuses while a page is missing
    Given 47 of 48 pages built
    When page runs
    Then the exit code is 2, stderr says "not built yet" and no pairs.json is written

  # Backed by: tests/test_ux_blind.py::test_page_refuses_a_page_that_names_a_model
  Scenario: Page refuses a page that names a model
    Given a stored page containing "Made by Claude"
    When page runs
    Then the exit code is 2, stderr says "<page id>.html names a model" and no blind.html is written

  # Backed by: tests/test_ux_blind.py::test_page_writes_to_out_when_given
  Scenario: Page writes to --out when given
    Given 48 built pages
    When page --out <dir>/owner.html runs
    Then the file exists there, <root>/blind.html does not, and the output says "24 pairs"

  # Backed by: tests/test_ux_blind.py::test_blind_html_is_one_offline_document
  Scenario: The blind file is one offline document
    Given 48 built pages
    When page runs
    Then the file starts with <!doctype html>, has meta charset utf-8 and a viewport meta, has no http:// or https:// except the pages' xmlns, no link tag, no external script and no fetch call

  # Backed by: tests/test_ux_blind.py::test_blind_html_names_no_arm_model_block_sample_or_page
  Scenario: The blind file names no arm, model, block, sample or page
    Given 48 built pages
    When page runs
    Then the file contains no fable, opus, sonnet, claude, "sample", "block" or "arm" key, no brief id and no page id

  # Backed by: tests/test_ux_blind.py::test_blind_html_embeds_48_pages_as_sandboxed_srcdoc_iframes_labelled_a_and_b
  Scenario: The blind file embeds 48 sandboxed srcdoc iframes labelled A and B
    Given 48 built pages
    When page runs
    Then the file has 48 iframes whose srcdoc values equal the stored pages, each with sandbox="allow-scripts", width 390 and height 780, 24 captions "A" and 24 captions "B" in 24 templates

  # Backed by: tests/test_ux_blind.py::test_blind_html_shows_each_pair_in_its_stored_order_with_the_a_page_on_the_left
  Scenario: The blind file keeps the stored order with page A on the left
    Given pairs.json with 24 pairs
    When page runs
    Then the embedded deck lists the pair ids in the order of pairs.json with their brief title and description, and each template holds the left page before the right page

  # Backed by: tests/test_ux_blind.py::test_blind_html_has_the_buttons_back_save_and_the_fallback_textarea
  Scenario: The blind file has the answer buttons, back, save and a fallback
    Given 48 built pages
    When page runs
    Then the script offers "A is better", "B is better", "Back" and "Save results", builds a Blob named ux-blind-results.json with version 1 and a finished flag, reads and writes localStorage, shows "Pair n of 24" and a textarea, and offers no tie

  # Backed by: tests/test_ux_blind.py::test_blind_html_scripts_parse
  Scenario: The blind file's script is valid JavaScript
    Given 48 built pages
    When page runs
    Then node --check accepts the script

  # Backed by: tests/test_ux_blind.py::test_verdict_refuses_with_23_answers
  Scenario: Verdict refuses with 23 answers
    Given a results file with 23 of 24 pairs answered
    When verdict runs
    Then the exit code is 2, stdout is empty and stderr says "only 23 of 24 pairs are answered"

  # Backed by: tests/test_ux_blind.py::test_verdict_refuses_a_pair_answered_twice_or_an_unknown_pair
  Scenario: Verdict refuses a duplicated, unknown or non-A/B answer
    Given results with one pair twice, an unknown pair id, or the choice "tie"
    When verdict runs
    Then the exit code is 2 with "answered twice", "unknown pair" or "neither A nor B" and nothing on stdout

  # Backed by: tests/test_ux_blind.py::test_verdict_refuses_while_the_checklist_is_incomplete
  Scenario: Verdict refuses while the checklist is incomplete
    Given 24 answers and the checklist missing one block-1 page
    When verdict runs
    Then the exit code is 2 and stderr says "checklist is incomplete for 1 block-1 page"

  # Backed by: tests/test_ux_blind.py::test_verdict_refuses_without_a_pair_table
  Scenario: Verdict refuses without pairs.json
    Given no pairs.json
    When verdict runs
    Then the exit code is 2 and stderr says "run `page` first"

  # Backed by: tests/test_ux_blind.py::test_uq_fires_at_10_of_12_when_the_checklist_condition_holds
  Scenario: UQ fires at 10 of 12 when the checklist condition holds
    Given F preferred in 10 block-1 pairs and mean_F equal to mean_O
    When verdict --json runs
    Then quality_designer is fable-5-2@high and balanced_designer is opus-5-5@xhigh

  # Backed by: tests/test_ux_blind.py::test_uq_does_not_fire_at_9_of_12
  Scenario: UQ does not fire at 9 of 12
    Given F preferred in 9 block-1 pairs and equal checklist means
    When verdict --json runs
    Then quality_designer and balanced_designer are opus-5-5@xhigh

  # Backed by: tests/test_ux_blind.py::test_uq_does_not_fire_at_10_of_12_when_f_is_more_than_0_05_below_o_on_the_checklist
  Scenario: UQ does not fire when F is more than 0.05 below O on the checklist
    Given F preferred in 10 pairs, F credited 91 of 96 items and O 96 of 96 (a gap of 0.052)
    When verdict --json runs
    Then checklist_not_below is false and quality_designer is opus-5-5@xhigh

  # Backed by: tests/test_ux_blind.py::test_uq_still_fires_when_f_is_below_o_by_less_than_0_05
  Scenario: UQ still fires when F is below O by less than 0.05
    Given F preferred in 10 pairs, F credited 92 of 96 items and O 96 (a gap of 0.042)
    When verdict --json runs
    Then checklist_not_below is true and quality_designer is fable-5-2@high

  # Backed by: tests/test_ux_blind.py::test_ub_needs_11_of_12_and_the_same_checklist_condition
  Scenario: UB needs 11 of 12 and the same checklist condition
    Given F preferred in 11 block-1 pairs, then again with F credited 80 of 96 items and O 96
    When verdict --json runs
    Then balanced_designer is fable-5-2@high in the first case and opus-5-5@xhigh in the second

  # Backed by: tests/test_ux_blind.py::test_fast_always_uses_the_opus_designer
  Scenario: Fast always uses the Opus designer
    Given F preferred in all 24 pairs
    When verdict --json runs
    Then fast_designer is opus-5-5@xhigh

  # Backed by: tests/test_ux_blind.py::test_ud_fires_at_10_of_12_in_block_two_and_not_at_9
  Scenario: UD fires at 10 of 12 in block 2 and not at 9
    Given F preferred in 10, 9 and 12 block-2 pairs
    When verdict --json runs
    Then design_pass_default is true, false and true

  # Backed by: tests/test_ux_blind.py::test_block_counts_are_kept_apart
  Scenario: Block counts are kept apart
    Given F preferred in 7 block-1 pairs and 3 block-2 pairs
    When verdict --json runs
    Then block1_f_preferred_raw is 7 and block2_f_preferred_raw is 3, and the counted numbers are the same

  # Backed by: tests/test_ux_blind.py::test_mean_scores_are_credited_items_over_eight_per_page_over_twelve_pages
  Scenario: Mean scores are credited items over 8 per page over 12 pages
    Given F credited 60 items and O 72 over 12 block-1 pages each
    When verdict --json runs
    Then mean_F is 0.625 and mean_O is 0.75

  # Backed by: tests/test_ux_blind.py::test_verdict_counts_how_often_the_left_page_was_chosen
  Scenario: Verdict counts how often the left page was chosen
    Given 24 answers all A, then all B
    When verdict --json runs
    Then left_chosen is 24 of 24, then 0

  # Backed by: tests/test_ux_blind.py::test_the_text_verdict_prints_counts_means_the_left_bias_and_the_rule_outcomes
  Scenario: The text verdict prints counts, means, the left bias and the rule outcomes
    Given F preferred in 11 block-1 and 10 block-2 pairs, then in 5 and 5
    When verdict runs
    Then it prints "block 1 (F against O): F preferred in 11 of 12 counted (11 raw;", "mean_F 1.0000  mean_O 1.0000", "left page chosen n of 24", "UQ (quality): designer fable-5-2@high", "fast: designer opus-5-5@xhigh" and the design-pass line; with 5 and 5 it prints the Opus designer and "not a default; available on request, no benefit measured"

  # Backed by: tests/test_ux_blind.py::test_json_verdict_holds_scalars_only
  Scenario: The JSON verdict holds scalars only
    Given a complete set of answers
    When verdict --json runs
    Then every value is a number, boolean or string, and no page id or brief id appears

  # Backed by: tests/test_ux_blind.py::test_safety_stops_above_zero_is_a_refusal_even_with_stop_reason_end_turn
  Scenario: A safety stop is a refusal even when stop_reason is end_turn
    Given the fable designer's first call returns stop_reason "end_turn" and safety_stops 1
    When the design step runs
    Then that attempt is logged as not accepted with reason "refused" and stop_reason "end_turn" and safety_stops 1, and the design records attempts 2 and slot_failed true

  # Backed by: tests/test_ux_blind.py::test_an_error_attempt_is_retried_but_does_not_flag_the_slot
  Scenario: An API error attempt is retried but does not flag the slot
    Given the fable designer's first call returns is_error true with stop_reason "end_turn" and safety_stops 0
    When the design step runs
    Then that attempt is logged with reason "is_error", the design records attempts 2 and slot_failed false, and plan reports fable_flagged_slots 0

  # Backed by: tests/test_ux_blind.py::test_every_attempt_logs_stop_reason_and_safety_stops
  Scenario: Every attempt logs stop_reason and safety_stops
    Given one brief and the design step run
    When attempts.jsonl is read
    Then its 9 entries each hold stop_reason "end_turn" and safety_stops 0

  # Backed by: tests/test_ux_blind.py::test_is_refusal_reads_stop_reason_safety_stops_and_the_substring_net
  Scenario: A refusal is read from stop_reason, safety_stops and the substring net
    Given result objects with stop_reason "refusal", safety_stops 1 or 3, terminal_reason "model_refusal", subtype "error_refusal", and others with is_error true and api_error_status 429, safety_stops 0, null or true
    When each is checked
    Then the first five are refusals and the others are not

  # Backed by: tests/test_ux_blind.py::test_the_builder_prompt_forbids_browser_storage_identically_for_every_arm
  Scenario: The builder prompt forbids browser storage for every arm
    Given two design texts and no design
    When the builder prompts are built
    Then each contains "no browser storage (localStorage, sessionStorage, cookies, IndexedDB); keep all state in memory"

  # Backed by: tests/test_ux_blind.py::test_a_script_that_uses_browser_storage_is_invalid
  Scenario: A script that uses browser storage makes the page invalid
    Given scripts using localStorage.setItem, sessionStorage.getItem, indexedDB.open, document.cookie and an onclick handler calling localStorage.clear()
    When each page is sanitised
    Then each page is invalid with the reason "script uses browser storage"

  # Backed by: tests/test_ux_blind.py::test_a_plain_text_mention_of_browser_storage_outside_a_script_is_fine
  Scenario: A plain-text mention of browser storage outside a script is fine
    Given a paragraph saying "no localStorage, no cookie, no indexedDB" and a script with a variable named cookies
    When the page is sanitised
    Then the page is valid

  # Backed by: tests/test_ux_blind.py::test_a_pair_whose_f_page_comes_from_a_flagged_slot_counts_as_f_not_preferred
  Scenario: A pair whose F page comes from a flagged slot counts as F not preferred
    Given 11 block-1 pairs where the owner chose F, two of them from F slots with slot_failed true
    When verdict --json runs
    Then block1_f_preferred_raw is 11, block1_f_preferred_counted is 9, block1_pairs_flagged is 2, block1_pairs_changed is 2, and quality_designer and balanced_designer are opus-5-5@xhigh

  # Backed by: tests/test_ux_blind.py::test_without_flagged_slots_raw_and_counted_are_equal
  Scenario: Without flagged slots the raw and counted numbers are equal
    Given F preferred in 11 block-1 and 10 block-2 pairs and no flagged slot
    When verdict --json runs
    Then raw and counted are 11 and 10, no pair is changed and balanced_designer is fable-5-2@high

  # Backed by: tests/test_ux_blind.py::test_a_flagged_slot_whose_pair_the_owner_did_not_prefer_changes_nothing
  Scenario: A flagged slot in a pair the owner did not prefer changes nothing
    Given F preferred in 10 block-1 pairs and two flagged F slots in pairs where the other page won
    When verdict --json runs
    Then raw and counted are both 10, block1_pairs_flagged is 2, block1_pairs_changed is 0 and quality_designer is fable-5-2@high

  # Backed by: tests/test_ux_blind.py::test_rule_ud_uses_the_counted_number_of_block_two
  Scenario: Rule UD uses the counted number of block 2
    Given F preferred in 10 block-2 pairs, two of them from flagged F slots
    When verdict --json runs
    Then block2_f_preferred_counted is 8 and design_pass_default is false

  # Backed by: tests/test_ux_blind.py::test_the_left_bias_count_stays_on_the_raw_choices
  Scenario: The left-bias count stays on the raw choices
    Given all 24 answers are A and every F slot on the left is flagged
    When verdict --json runs
    Then left_chosen is 24

  # Backed by: tests/test_ux_blind.py::test_the_text_verdict_reports_raw_counted_and_changed_pairs_with_a_note
  Scenario: The text verdict reports raw, counted and changed pairs with a note
    Given 10 raw F preferences in each block, one flagged F slot in a preferred pair of each block
    When verdict runs
    Then it prints "F preferred in 9 of 12 counted (10 raw; 1 pair(s) with a flagged Fable slot, 1 changed by it)" for both blocks, a "NOTE: section 2 counts a Fable slot" line and designer opus-5-5@xhigh for UQ

  # Backed by: tests/test_ux_blind.py::test_a_non_null_api_error_status_is_an_infra_error
  Scenario: A non-null api_error_status is an infra error
    Given a result with api_error_status 529 and 20 output tokens, and one with api_error_status 429 and is_error true
    When each call is classified
    Then both are infra errors; a result with api_error_status null and 20 output tokens is not

  # Backed by: tests/test_ux_blind.py::test_a_failed_call_with_no_output_tokens_is_an_infra_error_without_a_status
  Scenario: A failed call with no output tokens is an infra error even without a status
    Given a spawn failure, a non-zero exit with no output, and is_error true with 0 output tokens
    When each call is classified
    Then each is an infra error

  # Backed by: tests/test_ux_blind.py::test_a_timeout_a_failure_with_output_and_a_normal_call_are_not_infra_errors
  Scenario: A timeout, a failure that produced output and a normal call are not infra errors
    Given a timed-out call, a call with is_error true and 50 output tokens, a normal call, and unparseable output from a clean exit
    When each call is classified
    Then none is an infra error

  # Backed by: tests/test_ux_blind.py::test_three_rate_limit_errors_leave_the_slot_runnable
  Scenario: Three rate-limit errors leave a slot runnable
    Given the fable designer's first 3 calls fail with api_error_status 429
    When design runs 3 times, then a fourth time without errors
    Then the first 3 runs exit 3 and log accepted false, infra_error true and api_error_status 429; plan shows exhausted_designs 0 and infra_waiting_designs 1; the fourth run stores ux-01-F-1 with attempts 4 and slot_failed false

  # Backed by: tests/test_ux_blind.py::test_three_attempts_that_are_not_infra_errors_still_exhaust_the_slot
  Scenario: Three attempts that are not infra errors still exhaust a slot
    Given a model that never prints the marker lines and one brief
    When design runs
    Then plan shows exhausted_designs 9 and infra_waiting_designs 0, and no attempt is logged as an infra error

  # Backed by: tests/test_ux_blind.py::test_the_first_infra_error_stops_the_invocation_with_exit_3_and_starts_nothing_more
  Scenario: The first infra error stops the invocation with exit 3
    Given every call of the fable designer fails with api_error_status 429 and one job
    When design runs
    Then it exits 3, exactly 1 call was made, and stderr has one line naming "design|ux-01|F|1" and "api_error_status 429"

  # Backed by: tests/test_ux_blind.py::test_build_and_checklist_stop_on_an_infra_error_too
  Scenario: Build and checklist stop on an infra error too
    Given every builder call, then every fable-judge call, fails with api_error_status 429
    When build runs, then checklist runs
    Then each exits 3 after exactly 1 call, with a stderr line "infra error on build|" or "infra error on checklist|"

  # Backed by: tests/test_ux_blind.py::test_a_failed_call_with_no_output_and_no_status_stops_the_invocation_too
  Scenario: A failure with no output and no status stops the invocation too
    Given every fable designer call fails with is_error true, no output tokens and no api_error_status
    When design runs
    Then it exits 3 after 1 call, stderr says "api_error_status none", and the attempt is logged with infra_error true and accepted false

  # Backed by: tests/test_ux_blind.py::test_a_refusal_that_comes_back_with_is_error_is_not_an_infra_error
  Scenario: A refusal with is_error is not an infra error
    Given the fable designer's first call returns stop_reason "refusal", is_error true and 0 output tokens
    When design runs
    Then it exits 0, the attempt is logged with reason "refused" and infra_error false, and the design records attempts 2 and slot_failed true

  # Backed by: tests/test_ux_blind.py::test_plan_text_shows_the_slots_waiting_only_on_infra_errors
  Scenario: Plan shows the slots waiting only on infra errors
    Given one design slot whose only attempt was an infra error
    When plan runs
    Then it prints "slots waiting only on infra errors: 1 (1 designs, 0 builds, 0 checklist calls)"

  # Backed by: tests/test_ux_blind.py::test_the_builder_prompt_forbids_dialogs_form_submission_navigation_and_the_history_api_for_every_arm
  Scenario: The builder prompt forbids dialogs, form submission, navigation and the History API for every arm
    Given two design texts and no design
    When the builder prompts are built
    Then each contains "no alert, confirm or prompt dialogs; no form submission and no page navigation (switch screens by showing and hiding elements); no History API" followed by the same remaining rules

  # Backed by: tests/test_ux_blind.py::test_a_script_that_opens_a_dialog_is_invalid
  Scenario: A script that opens a dialog makes the page invalid
    Given scripts calling alert("hi"), window.alert(1), confirm('Sure?') and prompt ("Name"), and an onclick handler calling alert(1)
    When each page is sanitised
    Then each page is invalid with a dialog reason

  # Backed by: tests/test_ux_blind.py::test_a_script_that_uses_the_history_api_is_invalid
  Scenario: A script that uses the History API makes the page invalid
    Given scripts calling history.pushState, window.history.replaceState and history . pushState
    When each page is sanitised
    Then each page is invalid with the reason "script uses the History API"

  # Backed by: tests/test_ux_blind.py::test_a_script_that_navigates_the_page_is_invalid
  Scenario: A script that navigates the page makes the page invalid
    Given scripts with location.href = "next.html", window.location.href='#a', document.location.assign('x'), location.replace('x') and window.open('x'), and an onclick handler assigning location.href
    When each page is sanitised
    Then each page is invalid with a navigates reason

  # Backed by: tests/test_ux_blind.py::test_look_alike_calls_and_comparisons_are_fine
  Scenario: Look-alike calls and comparisons are fine
    Given a script with myAlert(1), confirmed(2), a variable prompts, x.alerts(), dialog.open(1), location.href == 'a', location.href === 'b', location.hash = '#a' and history.length
    When the page is sanitised
    Then the page is valid

  # Backed by: tests/test_ux_blind.py::test_a_plain_text_mention_of_dialogs_and_navigation_outside_a_script_is_fine
  Scenario: A plain-text mention of dialogs and navigation outside a script is fine
    Given a paragraph saying "No alert( or confirm( dialogs, no window.open( and no history.pushState, no location.href = x."
    When the page is sanitised
    Then the page is valid

  # Backed by: tests/test_ux_blind.py::test_reject_removes_the_page_and_build_lists_it_as_missing_again_without_printing_the_arm
  Scenario: Reject removes a page and build rebuilds it without printing the arm
    Given 48 built pages and the D page of ux-01 sample 1
    When reject --page <id> --reason "blank screen" runs, then plan and build
    Then stdout is exactly "rejected page <id>: blank screen", stderr is empty, the file and the pages.json entry are gone, plan shows builds_missing 1, and build makes 1 call that stores a page under a new id

  # Backed by: tests/test_ux_blind.py::test_reject_logs_one_counted_failed_build_attempt_for_the_slot
  Scenario: Reject logs one counted failed build attempt
    Given a built D page
    When reject runs
    Then attempts.jsonl holds one entry for slot "build|ux-01|D|1" with accepted false, infra_error false and reason "rejected: blank screen", and failures_of counts 1

  # Backed by: tests/test_ux_blind.py::test_rejections_count_toward_the_same_cap_as_other_failed_builds
  Scenario: Rejections count toward the same attempt cap
    Given a D page rejected and rebuilt three times in turn
    When build runs after the third reject
    Then no further builder call is made (2 calls in all) and plan shows builds_missing 1 and exhausted_builds 1

  # Backed by: tests/test_ux_blind.py::test_reject_also_drops_the_checklist_answers_of_that_page
  Scenario: Reject drops the checklist answers of that page
    Given a block-1 page with both judges' answers
    When reject runs
    Then its entry is gone from checklist.json

  # Backed by: tests/test_ux_blind.py::test_reject_of_an_unknown_page_is_refused
  Scenario: Reject refuses an unknown page id
    Given pages.json without deadbeef
    When reject --page deadbeef runs
    Then the exit code is 2, stdout is empty and stderr says "no page deadbeef"

  # Backed by: tests/test_ux_blind.py::test_reject_takes_the_evalkit_lock
  Scenario: Reject takes evalkit's lock
    Given another process holds evalkit's exclusive lock
    When reject runs
    Then the exit code is 2, stderr says "already writing" and the page is still in pages.json

  # Backed by: tests/test_ux_blind.py::test_page_refuses_without_a_render_check_file
  Scenario: Page refuses without a render-check file
    Given 48 built pages and no render-check.json
    When page runs
    Then the exit code is 2, stderr says "render-check.json is missing" and neither pairs.json nor blind.html is written

  # Backed by: tests/test_ux_blind.py::test_page_refuses_with_a_render_check_older_than_a_page
  Scenario: Page refuses a stale render-check file
    Given a render-check.json that is older than the newest page file
    When page runs
    Then the exit code is 2 and stderr says "render-check.json is older than a page file"

  # Backed by: tests/test_ux_blind.py::test_page_refuses_when_a_page_changed_after_the_check
  Scenario: Page refuses when a page changed after the check
    Given a fresh render-check.json and then one page file touched 5 seconds later
    When page runs
    Then the exit code is 2 and stderr says "older than a page file"

  # Backed by: tests/test_ux_blind.py::test_page_refuses_when_the_render_check_lists_a_failed_page
  Scenario: Page refuses when the render check lists a failed page
    Given a fresh render-check.json with passed false for one page
    When page runs
    Then the exit code is 2, stderr says "did not pass 1 page(s)" and names that page id

  # Backed by: tests/test_ux_blind.py::test_page_refuses_when_a_page_is_missing_from_the_render_check
  Scenario: Page refuses when a page is missing from the render check
    Given a fresh render-check.json that lacks one page id
    When page runs
    Then the exit code is 2, stderr says "did not pass 1 page(s)" and names that page id

  # Backed by: tests/test_ux_blind.py::test_page_accepts_a_fresh_render_check_that_passes_every_page
  Scenario: Page accepts a fresh render check that passes every page
    Given a render-check.json newer than every page, with passed true for all 48
    When page runs
    Then the exit code is 0 and blind.html is written

  # Backed by: tests/test_ux_blind.py::test_the_render_check_must_name_a_page_rebuilt_after_a_reject
  Scenario: A page rebuilt after a reject needs a new render check
    Given a passing render check, then a reject and a rebuild of one page
    When page runs
    Then the exit code is 2 and stderr says "older than a page file"

  # Backed by: tests/test_ux_blind.py::test_a_page_with_enough_text_and_no_errors_passes
  Scenario: A page with 20 characters of text and no errors passes the render check
    Given stats with 40 and with 20 visible characters, no errors, no canvas, svg or img
    When the page is judged
    Then it passes with no reasons

  # Backed by: tests/test_ux_blind.py::test_an_uncaught_error_on_load_fails_the_page
  Scenario: An uncaught error on load fails the render check
    Given stats with load_errors 1
    When the page is judged
    Then it fails with the reason "uncaught error on load"

  # Backed by: tests/test_ux_blind.py::test_an_uncaught_error_on_the_first_click_fails_the_page
  Scenario: An uncaught error on the first click fails the render check
    Given stats with click_errors 2
    When the page is judged
    Then it fails with the reason "uncaught error on first click"

  # Backed by: tests/test_ux_blind.py::test_a_page_with_under_20_characters_and_nothing_drawn_rendered_nothing
  Scenario: A page with under 20 characters and nothing drawn fails the render check
    Given stats with 19 and with 0 visible characters and no canvas, svg or img
    When the page is judged
    Then it fails with the reason "rendered nothing"

  # Backed by: tests/test_ux_blind.py::test_a_canvas_an_svg_or_an_img_counts_as_rendered
  Scenario: A canvas, an svg or an img counts as rendered
    Given stats with 3 visible characters and one canvas, one svg or one img
    When the page is judged
    Then it passes

  # Backed by: tests/test_ux_blind.py::test_every_failing_reason_is_reported
  Scenario: Every failing reason is reported
    Given stats with a load error, a click error and 0 visible characters
    When the page is judged
    Then it fails with 3 reasons

  # Backed by: tests/test_ux_blind.py::test_the_report_fails_unless_every_page_passed_and_there_is_at_least_one
  Scenario: The report passes only when every page passed and there is at least one
    Given reports for two passed pages, one passed and one failed page, and no page
    When the reports are built
    Then all_passed is true, false (checked 2, failed 1) and false; version is 1 and viewport is 390x780

  # Backed by: tests/test_ux_blind.py::test_messages_are_cut_to_120_characters_on_one_line
  Scenario: Error messages are cut to 120 characters on one line
    Given a message of 300 characters with a line break
    When it is shortened
    Then it is 120 characters long and has no line break

  # Backed by: tests/test_ux_blind.py::test_the_frame_is_sandboxed_without_same_origin_at_the_phone_viewport
  Scenario: The render check uses the owner's frame
    Given a page source with markup and an ampersand
    When the wrapper document is built
    Then it holds one iframe with sandbox="allow-scripts" and no allow-same-origin, width 390 and height 780, and the source HTML-escaped in srcdoc

  # Backed by: tests/test_ux_blind.py::test_the_check_reads_only_page_files_and_never_names_the_arm_mapping
  Scenario: The render check reads page files only
    Given the source of scripts/quality/check_ux_pages.py
    When it is read
    Then it never names pages.json, designs, attempts, pairs.json or checklist.json and reads only *.html files

  # Backed by: tests/test_ux_blind.py::test_the_report_can_be_read_by_the_page_gate_in_the_shape_ux_blind_expects
  Scenario: The render-check report has one scalar-only entry per page id
    Given a report for page a1
    When it is built
    Then its pages object is keyed by page id and every value of an entry is a number, string or boolean

  # Backed by: scripts/quality/check_ux_pages.py::check_ux_pages_render
  Scenario: The render check loads every page in the owner's frame and fails blank or broken ones
    Given a root with four pages: one that renders text and a working button, one that throws on load, one that is blank, and one whose button throws
    When check_ux_pages.py runs headless against the root
    Then the first page passes; the second fails with an uncaught error on load, the third fails with rendered nothing, the fourth fails with an uncaught error on first click; the exit code is 1 and render-check.json lists every page id with scalar values only

  # Backed by: tests/test_ux_blind.py::test_designer_and_builder_children_start_with_the_advisor_switch_whatever_the_parent_says
  Scenario: Designer and builder children start with the advisor switched off
    Given a parent environment where CLAUDE_CODE_DISABLE_ADVISOR_TOOL is "0"
    When the design and build steps run for one brief
    Then every designer child and every builder child saw CLAUDE_CODE_DISABLE_ADVISOR_TOOL equal to "1"
