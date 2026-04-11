# FlexAI for Social Encounters

**Source:** *FlexAI Guidebook* (Infinium Game Studios, 2020-08-17 v1.5), pages 260–265.
Verbatim text extracted from the PDF via PyMuPDF. This file exists so that the
program's behavior is traceable back to the rulebook.

---

## About Social Encounters

Combat encounters rely upon confrontation and damage to determine the outcome.
Social encounters use words as the weapons.

Social Encounters are, generally speaking, any non-combat interaction between
the adventuring party and one or more creatures who speak one or more languages
that the PCs do.

### Limitations

By nature, social encounters are more complex than combat encounters. No matter
how detailed and thorough the attempt, AI for social encounters will always
require some interpretation as it applies to the specific aspects of the
encounter being played.

---

## How to Use FlexAI for Social Encounters

### Sanity Checks & Rerolls

Generally speaking, if something "feels wrong", reroll it.

More specifically, if the Outcome determined by FlexAI does not apply (e.g.,
the NPC in question lacks any specialized knowledge that a Subject Info might
be used to uncover) or are inappropriate to the circumstances (e.g., Turn
Hostile when the NPC in question is a pacifist), reroll the result to determine
a more appropriate outcome.

### Starting Points

Far more so than with Combat Encounters, the rules for FlexAI Social Encounters
should be considered a starting point for a seasoned GM to expand upon
intelligently and reasonably.

Specifically, the DCs cited in the following FlexTables should be considered
the minimum, or a reasonable average, value; obviously, the value used in a
particular test should reflect much more context than a static book can
possibly predict.

### Behavior Common Concepts

There are some basic concepts for the FlexAI implementation of social encounter
AI that bear some explaining.

FlexAI for Social Encounters helps you determine the following things:

- What **Choices** are possible when interacting with the NPC(s);
- How **Difficult** (i.e., the DC) each Choice is, depending on the level of
  the party;
- What Result occurs during a **Successful** interaction check;
- What Result occurs during a **Failed** interaction check.

To help determine the above, you must know three things about the social
interaction:

- The **Social Role** played by the NPC(s) being interacted with;
- The **Role Size** of the NPC(s);
- The **Social Context** of the interaction.

Taken together, the above three elements will allow you to determine which
page's tables to use to simulate the NPC's behavior.

---

## Social Roles

A **Social Role** is a description of the utility of the NPC relative to the
adventuring party. This is partly a measure of the NPC's relationship with the
party or its members, and partly a representation of the role in the story the
GM intends for the character.

Some adventuring products will come with the Social Role of an NPC already
described. For others, you will have to make an assessment as to what makes
the most sense; to help guide that determination, each Role contains several
examples.

### Table 11: Social Roles

| Role         | Description |
|--------------|-------------|
| **Ally**         | Someone who is deeply devoted to one or more PCs, or is committed to the cause of the party as a whole. Can also be someone whose life or livelihood you have saved or improved. *Examples: Hireling, devotee, squire, relative.* |
| **Asset**        | A key character who is intentionally part of the plot of the story. Can be at the session, module, or campaign level of detail; the deciding factor is if this person has information that they can share to help progress the narrative. *Examples: The wizard who hires the party to go on a quest; the courtesan who knows which merchants have sampled the brothel's offerings.* |
| **Acquaintance** | A positive relationship, but one less in strength and more casual than an Ally. *Examples: A fellow faction member, a shopkeeper with whom you have done business, or a tavern owner who knows you.* |
| **Opponent**     | Someone who is perhaps not actively engaged in combat with you at the moment, but is hostile to your party or at odds with their aims fundamentally. *Examples: An evil NPC, a rival guild leader, or the guard beyond whom lies the princess.* |
| **Bystander**    | Someone completely neutral to you and either ambivalent about or ignorant of your cause. Such a person is neither helpful nor hostile initially. *Examples: Any passerby on the street; anyone with whom you have no existing relationship and who has no reason to know who you are.* |

---

## Social Role Sizes

In addition to the Social Role described above, each NPC and creature also has
a **Role Size**.

This is identical in nature and purpose to the Role Variant characteristics
for monsters in combat AI described earlier. For monsters who might also
communicate, simply use the Role Size you determined for them (or which was
provided for them).

For NPCs, use the following guidance if the Role Size is not provided as part
of their profile.

- **Normal** — Use as a default, or if no other description below applies.
- **Minion** — A minor character, passerby, or a creature with an Intelligence
  value of 8 or lower.
- **Elite** — A key character, prominent faction member, or significant NPC.
- **Solo** — A major character in the story, a leader of a faction, or someone
  who has a very close relationship with the PCs.

---

## Social Contexts

While Social Role is the single most important determinant of how an NPC will
interact with the PCs, also of huge significance is the **Context** of the
interaction.

A conversation taking place amidst a battlefield is markedly different than
one occurring in a tavern late at night, and will undoubtedly produce different
results, no matter what the relationship between the party and a character!

### Table 12: Social Contexts

| Context              | Description |
|----------------------|-------------|
| **Combat**               | There is fighting taking place. Note that the fighting need not necessarily involve the PCs fighting the NPC(s), and does not necessarily mean that both the PCs and the NPC(s) are fighting other creatures. Any combat taking place near the social interaction qualifies. In cases where the PCs are actively engaged in combat with the NPC(s) they would want to have a conversation with, use the rules inherent in your game's system to determine how to start a conversation without suffering additional blows before using FlexAI for Social Encounters. |
| **Lull in Fighting**     | Combat has occurred recently, but there is no active combat at the moment. A battlefield with a brief lull in the fighting, or peace negotiated shakily between two parties, qualifies. |
| **Long Rest**            | The parties to the conversation are gathered around a campfire, are laying down in a communal sleeping area in a church, or are otherwise in a situation where all are ready for a long (i.e., overnight, typically) rest. |
| **Short Rest**           | The PCs and the NPC(s) are in a tavern, bath house, sauna, spa, or other establishment where a short (i.e., 1-4 hours) rest or relaxation is occurring. |
| **Formal Gathering**     | The people involved are attending a church service, wedding, banquet, celebration, or other formal gathering. |
| **Informal Gathering**   | The party and its NPC(s) are participating in a shop, a festival, an impromptu party in a tavern, or other informal gathering. |
| **Passing By**           | Use this Context if no other category applies, or if the PCs are merely greeting the NPC(s) in passing on the street, on a road, or in town. |

---

## Social Interaction Choices

**Interaction Choices** refer to the set of possible interactions that can be
attempted in a conversation between the PCs and one or more NPCs.

### Table 13: Social Choices

| Outcome          | Description | Skill Analogues |
|------------------|-------------|-----------------|
| **Diplomacy**    | Peacefully and gracefully introduce a notion and attempt to inspire a favorable response. | Persuasion, discussion, investigation, insight |
| **Intimidate**   | Aggressively force information or an opinion out of your conversation partner. | Intimidation |
| **Sense Motive** | Detect lies, or attempt to understand if there is something meaningful behind a statement. | Perception, insight, investigation when attempting to determine veracity of a statement or the underlying motives of someone |
| **Mislead**      | Provide a response, or seed information, that you know to be untrue. | Deception, bluff |
| **Gather Info**  | Obtain information in a general sense about an event, character, faction, establishment, or other local or immediate person, place, thing, or action. | Investigation, Knowledge (Local) |
| **Subject Info** | Expand your knowledge about certain subjects beyond what a lay person might be aware of. | Any other Knowledge or Profession skill |

### Using Social Choice Options

Each combination of Social Role, Role Size, and Social Context contains a set
of Choices. The FlexTable that describes these Choices serves a dual function:

- The **d100 roll results on the left side** of the FlexTable are used when
  determining what action the NPC might take when it is their "turn" in the
  conversational volley.
- The **columns on the right side** of the FlexTable represent which actions
  the PCs can feasibly take to interact with the NPC, and lists the DCs for
  doing so based on which Quadded Challenge rank the PCs qualify to be in.

The lower value is used for systems like 5E/Fifth Edition, and the higher
value is used for more scalable systems like Pathfinder and Pathfinder Second
Edition.

Note that this information is typically hidden from the PCs, so they are not
entirely certain which Choices might be feasible. When playing a traditional
tabletop gaming group, only the GM/DM should determine and be aware of these
options.

> As with every other aspect of FlexAI, the values and tools provided are
> intended merely as a starting point. Use common sense, and mix in your own
> expectations, needs, and railroading to guide you when setting DCs and
> options available for Choices in a social encounter.

### Unavailable Choices

Choices listed as "n/a" for their DC values indicate that it is not feasible
to successfully interact with the NPC in that manner, in this context.

More mechanically, if the PCs attempt a Social Choice that is listed as "n/a"
or that does not contain a DC listing, the attempt **automatically fails**.

---

## Social Encounter Results

Whenever the PCs attempt a social interaction with an NPC, you can use FlexAI
to determine whether that attempt is successful or fails. Note that success
or failure terminology is used from the perspective of the PCs: specifically,
are they able to do what they wanted to do, and get what they wanted to get
out of, the interaction?

The list below, and used herein, is not intended to be, and cannot be, a
complete description of every possible social interaction. Vagaries of story
context, communication method, personalities, and senses of humor make it
impossible to cover every situation, but in the hands of a good GM, the
following list of possible Results will provide a comprehensive framework for
storytelling mechanics.

### Leniency / Immediacy

Each of the "bad" Results below describes a possibility for the GM to
underscore the failure by making the consequences immediate, or to show
leniency and grant further options to recover from the failure.

These options should be selected based on how the GM feels about the social
encounter, what is intended for the party, and potentially by the degree of
failure.

It is suggested that a **critical failure** in a social interaction trigger
the more immediate consequence described.

### Table 14: Social Encounter Results

| Outcome               | Description |
|-----------------------|-------------|
| **Turns Hostile**     | The NPC turns openly hostile to you. At the GM's discretion, this could immediately trigger a combat encounter, or perhaps the PCs have one final chance to defuse the situation. |
| **Leaves**            | The NPC is affronted, bored, busy, suspicious, or otherwise not interested in talking with you any longer. They attempt to leave. At the GM's discretion, the NPC may leave immediately, or perhaps the PCs can make an attempt at regaining their trust or interest. |
| **Ignores You**       | The NPC has other things on their mind, or finds your drivel exhausting. They ignore, or pretend to ignore, your attempts to interact. At the GM's discretion, the NPC may still be listening, and further successes may change their mind. |
| **Helps**             | Whether in combat, in undertaking a task, or in aligning with a cause, the NPC agrees to help in whatever enterprise the party is discussing. Depending on the seriousness of the extant relationship with the party, this "help" could take many forms. It is rarely intended to represent that the NPC would put their life on the line to assist, however. |
| **Answers Grudgingly**| With resistance, and perhaps by accident, the NPC will answer the question posed, providing minimal information in satisfaction of the request. |
| **Answers**           | Neither overly helpful nor overtly belligerent, the NPC will address the matter being discussed. |
| **Answers Willingly** | Gladly and helpfully, and providing a good deal of detail, the NPC will answer the question to the best of their ability. |
| **Volunteers Info**   | Treat as "Answers Willingly", but the NPC will also provide additional information. This could be further information about the general topic, or simply more information about something that they recalled. |
| **Can Grant Plot Clue** | Assuming they have such information to provide, the NPC may discuss major clues or significant information related to the overall plot or story that is in process. The next time a successful result is achieved, the NPC also includes this information. This is very similar to "Reveals Plot Clue" below, except that the success is conditional upon further successful interactions. |
| **Challenges You**    | This is not a mortal combat level of dueling challenge, but rather a social challenge: to proceed further with this NPC, the party must make a successful social check (use one of the Choices available depending on the tack the party wishes to take). Failure means the NPC Leaves immediately. Critical failure, or at the GM's discretion, means the NPC may even Turn Hostile. |
| **Questions Motives** | The NPC is suspicious of why the PCs are asking them these questions, or speaking of things in a certain manner. The PCs must defend their perspective by making an opposed check (use mechanics appropriate for the interaction, e.g., Sense Motive). Treat failure as an Ignores You result. Treat critical failure as a Leaves result. Success means the party can continue with their discussion. Critical success, at the GM's discretion, may convert this into an Answers or even an Answers Willingly result. |
| **Reveals Plot Clue** | Treat this as "Can Grant Plot Clue", except that the revelation is automatic. |
| **Red Herring**       | From the party's perspective, this appears to be "Answers Willingly" or even "Volunteers Info". However, the information provided, while accurate, is completely unrelated to the question, or what the PCs are attempting to ascertain. |
| **Lies**              | From the party's perspective, this appears to be "Answers Grudgingly" or even "Answers". However, the information is knowingly fraudulent, and completely wrong. If the PCs are suspicious, they can attempt to determine if the information is a lie as normal. |
