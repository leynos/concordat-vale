Feature: Package the Concordat Vale style
  Scenario: Build a distributable archive
    Given a clean staging project containing the styles tree
    When I run stilyagi zip for that staging project
    Then a zip archive is emitted in its dist directory
    And the archive includes the concordat content and config
    And the archive contains a .vale.ini referencing the concordat style

  Scenario: STILYAGI environment overrides influence the CLI
    Given a clean staging project containing the styles tree
    And STILYAGI_ environment variables are set
    When I run stilyagi zip for that staging project
    Then a zip archive is emitted in its dist directory
    And the archive includes the concordat content and config
    And the archive .vale.ini uses the STILYAGI_ environment variable values
