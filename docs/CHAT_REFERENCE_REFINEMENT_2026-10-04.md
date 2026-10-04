# Chat reference refinement

The web cabinet was compared with the publicly available ChatGPT start-screen screenshot published by BleepingComputer and the official ChatGPT page. Direct browser runtime and Windows Computer Use were unavailable, so no live visual inspection of a signed-in ChatGPT session is claimed.

Reference: https://www.bleepingcomputer.com/news/artificial-intelligence/openai-confirms-chatgpt-is-down-as-logins-and-signups-fail/

Changes:

- Black canvas and compact pill composer replace the larger charcoal input panel. The textarea grows with content to a bounded height and then scrolls.
- Primary navigation contains Today, Assistant, Quotes, Projects and Clients. Work, Library and Account use named expandable groups; the active destination automatically reveals its group.
- Desktop navigation can be collapsed. Mobile keeps its existing drawer and backdrop. Collapse buttons expose their state and controlled region to assistive technology.
- Estimates and Assistant have a central mode switch that invokes the existing navigation handlers. It is hidden during authentication.
- Manual creation, catalog and assistant shortcuts appear below the request input. They use existing product actions and appear only where writing is permitted.
- The mobile submit control retains its accessible text while displaying an icon. File selection continues to report the filename through the existing status region.
- Backend rules, subscription behavior and Android APK are unchanged.

Validation: web build and JS syntax passed. Browser integration passed creation, editor preview/undo, approvals, project payments, PDF and public intake. Added assertions cover desktop sidebar collapse, expandable navigation groups, textarea growth, 320/390px overflow and mobile drawer/backdrop interaction. Streaming assistant integration passed preview/apply/undo, reload retries, conversation contexts, file preparation and draft persistence. Real API operations use an isolated local fixture with mocked model responses.
