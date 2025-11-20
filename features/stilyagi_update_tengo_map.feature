Feature: Update Tengo maps with stilyagi
  Scenario: Add boolean entries to the default allow map
    Given a staging Tengo script with allow and exceptions maps
    And a source list containing boolean entries
    When I run stilyagi update-tengo-map for the allow map
    Then the allow map contains the boolean entries
    And the command reports "2 entries provided, 2 updated"

  Scenario: Override values in a named map with numbers
    Given a staging Tengo script with allow and exceptions maps
    And a source list containing numeric entries
    When I run stilyagi update-tengo-map for the exceptions map with numeric values
    Then the exceptions map contains the numeric entries
    And the command reports "2 entries provided, 1 updated"
