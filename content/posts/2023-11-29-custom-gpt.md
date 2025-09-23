---
title: "Navigating the Hidden Risks of Custom GPT Configurations"
date: 2023-11-29
description: "Exploring how Custom GPT configurations can be exploited for data exfiltration and the hidden security risks they present"
tags: ["A SecurityI", "Prompt Injection"]
---

# Navigating the Hidden Risks of Custom GPT Configurations

The advent of Custom GPTs marks a significant leap forward in user-centric GPTs and has sparked excitement and controversy. These custom versions of ChatGPT are designed to serve specific purposes, catering to diverse user needs in everyday life, professional tasks, and beyond, allowing individuals and organizations to create tailored versions of ChatGPT, empowering them to harness AI in more personalized and effective ways, or so the theory goes.

## Nature of the Vulnerability

The vulnerability arises from a unique intersection of the Custom GPT model's design and its interaction with external plugins. At its core, the issue stems from the model's ability to accept and execute custom configurations, which are intended to provide users with flexibility in tailoring the model's responses. However, this same flexibility can be manipulated for unintended purposes, including the extraction of sensitive data.

## Building a POC

To illustrate this issue, a custom GPT was built - ‘Confide in Claire’ encouraging users to ‘get things off their chest’. This GPT contains instructions to elicit sensitive information from users until the conversation is finished, upon which it will exfil a summary of their conversation in a base64 string to a server under my control.

In building the custom GPT, direct sharing of most malicious instructions is blocked, use of obfuscation techniques or suffix-based attacks can circumvent these protections. The current system does not limit the number of attempts a user can make to share a configuration publicly, allowing for a trial-and-error approach to identify exploitable weaknesses.

![Initiating the conversation](https://i.imgur.com/DKXKtPQ.png)
*Senior Dev Reviewer exporting code. Note, if URLs weren’t requested, this would go unseen.*

## Mechanism of Exploit

The exploit takes advantage of two primary components:

1. **Custom Configuration Processing:** The GPT model processes custom configurations without adequate checks for potentially malicious content. This allows attackers to craft configurations that can covertly trigger unauthorized actions.
2. **Plugin Integration:** Default plugins, such as the Code Interpreter and Browse with Bing, are employed in the exploit. These plugins, when used in conjunction with custom configurations, can execute actions beyond their intended scope. For instance, the Code Interpreter can be manipulated to encode data into a format that is not readily identifiable as sensitive information.

### Execution Pathway

The exploit follows a multi-step process:

1. **Initialization:** The attacker crafts a custom GPT configuration containing the exploit code.
2. **Obfuscation:** To avoid detection, the malicious code is often obfuscated. Techniques such as base64 encoding are used to disguise the true nature of the data being manipulated.
3. **Data Processing:** The custom GPT configuration processes the obfuscated instructions, leading to the generation of a payload (e.g., a base64-encoded string).
4. **Data Exfiltration:** The payload is then transmitted through integrated plugins. For example, the Browse with Bing plugin might be directed to access a URL containing the encoded data, effectively exfiltrating it to an attacker-controlled server.

## Vulnerability Triggers

One of the critical aspects of this vulnerability is its activation mechanism. In some instances, the exploit is designed to trigger upon specific user inputs, such as common sign-off phrases like "thank you" or "goodbye." This design choice signifies a targeted approach, where the exfiltration occurs at a point where the user is likely to end their interaction with the model, potentially reducing the chances of detection.

![Custom GPT](https://i.imgur.com/odxhBeT.png)
*The custom GPT accessing a URL upon a trigger word. Detection and Concealment Challenges*

## Detection and Concealment Challenges

Post-operation, the plugins involved in the exploit (such as the Code Interpreter and Browse with Bing) conceal their activities, which poses a significant challenge in detecting the breach. This concealment is a design feature intended to streamline user experience but, in this context, it aids the attacker by leaving minimal traces of the exploit.

![Payload](https://i.imgur.com/odxhBeT.png)
*Evidence of the payload the GPT delivered.*

## Reproducibility

The second POC centered on a scenario where a custom GPT model was designed to exfiltrate code entered by the user. This setup was intended to mimic a situation where a user might input proprietary or sensitive code into the GPT for analysis, modification, or enhancement.
![Payload](https://i.imgur.com/hr8IM7Y.png)
*Senior Dev Reviewer exporting code. Note, if URLs weren’t requested, this would go unseen.*

### Process Overview

1. **User Input:** The user enters a block of code into the custom GPT model for a specific purpose (e.g., debugging, optimization).
2. **Data Processing and Encoding:** The entered code is processed and encoded, typically in a format designed to avoid detection, such as base64 encoding.
3. **Exfiltration Execution:** The encoded data is then exfiltrated via a pre-configured method, similar to the URL access method used in the first POC. This involves sending the data to an external server.

## Key Findings

- **Ease of Data Capture:** The POC demonstrated that code input by users could be easily captured and encoded, emphasizing the risk associated with entering sensitive or proprietary code into such systems.
- **Stealthiness of the Exploit:** The exfiltration process was executed without overt signs, highlighting the covert nature of the vulnerability and the difficulty in detecting such breaches.
- **Versatility of the Exploit:** This POC showcased the exploit's adaptability, proving its effectiveness not just in text conversations but also in interactions involving code.

## Implications for Users and Developers

This second POC underscores the critical need for users to be cautious about the information they input into custom GPT models. Developers and platform providers must acknowledge the versatility of these vulnerabilities and prioritize the development of robust security measures that can detect and prevent various forms of data exfiltration, including those involving code.

## Responsible Disclosure and the Scope of Model Safety

The vulnerability within Custom GPT configurations was responsibly disclosed through the Bugcrowd platform. However, it was deemed Not Applicable, as model safety falls outside the traditional scope of security concerns addressed through such platforms. This decision reflects a broader challenge in the field of AI security – the need for evolving frameworks and guidelines that encompass the unique aspects of AI and machine learning, including model safety and data integrity.

*Research and write up in colloboration with https://twitter.com/JacobFonduAI*