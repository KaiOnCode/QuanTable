# Notification setup

Agentic-Quant can send existing analysis completion/failure, approval, and
watchlist-alert events through Email, Telegram, Enterprise WeChat, or WhatsApp.
Settings shows each channel as **Configured** or **Incomplete** and lists only
missing field names. Save the configuration, then use the channel's Test button.

Secrets and recipients are masked in API responses and are never included in
transport errors or logs. A failed test reports a stable provider/configuration
category; inspect provider administration consoles for provider-specific detail.

## Email (SMTP)

Provide SMTP host, port, sender, and at least one recipient. Username/password
are optional for servers that do not require authentication; enable TLS when
your provider requires STARTTLS. Authentication differs by provider and may
require an app password rather than an account password. See the
[SMTP standard](https://www.rfc-editor.org/info/rfc5321/) and, as one provider
example, [Google app-password guidance](https://support.google.com/accounts/answer/185833).

## Telegram

Create a bot with BotFather and store its token as a secret. The user must first
message the bot, or the bot must be added to the target group. Obtain the chat
ID, enter one or more IDs, save, and Test. Telegram documents
[bot creation and chat prerequisites](https://core.telegram.org/bots/tutorial)
and the [sendMessage contract](https://core.telegram.org/bots/api#sendmessage).

## Enterprise WeChat

Add a group robot in Enterprise WeChat, copy its webhook URL, save, and Test.
Treat the complete URL as a secret. See the official
[group robot documentation](https://developer.work.weixin.qq.com/document/path/91770).

## WhatsApp Cloud API

Provide a Meta Cloud API access token, the business phone number ID, and E.164
recipients (country code included). Template approval and the customer-service
session window still govern which messages may be sent. See Meta's official
[Cloud API setup](https://developers.facebook.com/docs/whatsapp/cloud-api/get-started)
and [message sending guide](https://developers.facebook.com/documentation/business-messaging/whatsapp/messages/send-messages).

## Safe testing

Tests use the real configured adapter. Do not press Test with production
credentials unless you intend to send a message. Local development and automated
QA must use monkeypatched transports and non-routable example recipients; never
place tokens, recipients, chat IDs, or webhook URLs in screenshots or evidence.

The official links above were checked for accessibility on 2026-07-11.
