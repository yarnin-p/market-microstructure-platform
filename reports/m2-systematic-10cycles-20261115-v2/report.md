# TASK 002.2 — Systematic expansion

{
  "run_id": "m2-systematic-10cycles-20261115-v2",
  "primary_definition": "OBSERVED_SESSIONS_FIRST / HIGH_LOW_ONLY / NO_MECHANICAL_GAP",
  "selected_opportunities": 240,
  "cycles_processed": 10,
  "complete_cycles": 10,
  "complete_trade_windows": 240,
  "primary_events": 40,
  "verified_observed_first_events": 40,
  "zero_event_opportunities": 200,
  "strict_full_cycle_status": "UNAVAILABLE_NO_INDEPENDENT_OVERNIGHT_VERIFICATION",
  "strict_denominator": 0,
  "session_events": {
    "RTH": 21,
    "AH": 9,
    "PRE": 10
  },
  "unique_securities": 212,
  "repeated_securities": 26,
  "sampling": "24 per cycle, daily stratified SRS; full selected sample only",
  "requests": 351,
  "pages": 351,
  "decoded_bytes": 643037535,
  "api_errors": 0,
  "sensitivities": {
    "odd_events": 43,
    "primary_events": 40,
    "odd_added_events": 3,
    "changed_touch_timestamps": 19
  },
  "statuses": {
    "ENGINEERING_VALIDATED": true,
    "DATA_COVERAGE_VALIDATED": true,
    "PILOT_RESULTS_AVAILABLE": true,
    "RESEARCH_STATISTICALLY_VALIDATED": false
  }
}

## Coverage by cycle

[
  {
    "cycle_id": "2026-05-27",
    "selected": 24,
    "complete": 24,
    "observed_first_denominator": 24,
    "events": 5,
    "verified_events": 5,
    "zero_event": 19,
    "sessions": {
      "RTH": 4,
      "PRE": 1
    },
    "primary_outcomes": {
      "forward": {
        "5m": {
          "events": 5,
          "uncensored": 4,
          "censored": 1,
          "mean": -0.010267009939353916,
          "median": -0.009448111086210034,
          "min": -0.04656206148743462,
          "max": 0.024390243902439025
        },
        "15m": {
          "events": 5,
          "uncensored": 3,
          "censored": 2,
          "mean": -0.022063298769425324,
          "median": -0.009470198675496689,
          "min": -0.08942467151422376,
          "max": 0.03270497388144447
        },
        "30m": {
          "events": 5,
          "uncensored": 2,
          "censored": 3,
          "mean": 0.008065880728521945,
          "median": 0.008065880728521945,
          "min": 0.0045423574835339545,
          "max": 0.011589403973509934
        },
        "60m": {
          "events": 5,
          "uncensored": 2,
          "censored": 3,
          "mean": 0.0053748610595124036,
          "median": 0.0053748610595124036,
          "min": -0.009084714967067909,
          "max": 0.019834437086092716
        },
        "session_end": {
          "events": 5,
          "uncensored": 5,
          "censored": 0,
          "mean": 0.04872120822958307,
          "median": 0.008278145695364239,
          "min": -0.10919760173491516,
          "max": 0.3281853281853282
        },
        "cycle_end": {
          "events": 5,
          "uncensored": 5,
          "censored": 0,
          "mean": 0.05425762869137666,
          "median": 0.008278145695364239,
          "min": -0.08151549942594719,
          "max": 0.3281853281853282
        }
      },
      "barriers": {
        "0.03/0.03": {
          "NEITHER": 2,
          "UPSIDE_FIRST": 3
        },
        "0.05/0.03": {
          "NEITHER": 3,
          "DOWNSIDE_FIRST": 2
        },
        "0.10/0.05": {
          "NEITHER": 3,
          "DOWNSIDE_FIRST": 1,
          "UPSIDE_FIRST": 1
        }
      },
      "excursion_events": 5,
      "excursion_censored": 0
    }
  },
  {
    "cycle_id": "2026-05-28",
    "selected": 24,
    "complete": 24,
    "observed_first_denominator": 24,
    "events": 4,
    "verified_events": 4,
    "zero_event": 20,
    "sessions": {
      "PRE": 3,
      "RTH": 1
    },
    "primary_outcomes": {
      "forward": {
        "5m": {
          "events": 4,
          "uncensored": 3,
          "censored": 1,
          "mean": -0.06941859798322175,
          "median": -0.08759183014450633,
          "min": -0.1039426523297491,
          "max": -0.016721311475409836
        },
        "15m": {
          "events": 4,
          "uncensored": 0,
          "censored": 4,
          "mean": null,
          "median": null,
          "min": null,
          "max": null
        },
        "30m": {
          "events": 4,
          "uncensored": 1,
          "censored": 3,
          "mean": -0.017921146953405017,
          "median": -0.017921146953405017,
          "min": -0.017921146953405017,
          "max": -0.017921146953405017
        },
        "60m": {
          "events": 4,
          "uncensored": 1,
          "censored": 3,
          "mean": -0.053763440860215055,
          "median": -0.053763440860215055,
          "min": -0.053763440860215055,
          "max": -0.053763440860215055
        },
        "session_end": {
          "events": 4,
          "uncensored": 2,
          "censored": 2,
          "mean": -0.050052294494388624,
          "median": -0.050052294494388624,
          "min": -0.06426229508196721,
          "max": -0.035842293906810034
        },
        "cycle_end": {
          "events": 4,
          "uncensored": 4,
          "censored": 0,
          "mean": -0.032482479038267224,
          "median": -0.0517888532001424,
          "min": -0.1231264033011712,
          "max": 0.0967741935483871
        }
      },
      "barriers": {
        "0.03/0.03": {
          "UPSIDE_FIRST": 2,
          "DOWNSIDE_FIRST": 2
        },
        "0.05/0.03": {
          "DOWNSIDE_FIRST": 3,
          "UPSIDE_FIRST": 1
        },
        "0.10/0.05": {
          "DOWNSIDE_FIRST": 3,
          "UPSIDE_FIRST": 1
        }
      },
      "excursion_events": 4,
      "excursion_censored": 0
    }
  },
  {
    "cycle_id": "2026-05-29",
    "selected": 24,
    "complete": 24,
    "observed_first_denominator": 24,
    "events": 5,
    "verified_events": 5,
    "zero_event": 19,
    "sessions": {
      "RTH": 2,
      "AH": 2,
      "PRE": 1
    },
    "primary_outcomes": {
      "forward": {
        "5m": {
          "events": 5,
          "uncensored": 2,
          "censored": 3,
          "mean": 0.0945193171608266,
          "median": 0.0945193171608266,
          "min": 0.0380952380952381,
          "max": 0.1509433962264151
        },
        "15m": {
          "events": 5,
          "uncensored": 2,
          "censored": 3,
          "mean": 0.06606132075471698,
          "median": 0.06606132075471698,
          "min": 0.0,
          "max": 0.13212264150943395
        },
        "30m": {
          "events": 5,
          "uncensored": 1,
          "censored": 4,
          "mean": -0.04716981132075472,
          "median": -0.04716981132075472,
          "min": -0.04716981132075472,
          "max": -0.04716981132075472
        },
        "60m": {
          "events": 5,
          "uncensored": 1,
          "censored": 4,
          "mean": -0.10372641509433962,
          "median": -0.10372641509433962,
          "min": -0.10372641509433962,
          "max": -0.10372641509433962
        },
        "session_end": {
          "events": 5,
          "uncensored": 4,
          "censored": 1,
          "mean": -0.06634649653772517,
          "median": -0.03930010940289054,
          "min": -0.1710377358490566,
          "max": -0.015748031496062992
        },
        "cycle_end": {
          "events": 5,
          "uncensored": 3,
          "censored": 2,
          "mean": -0.06827694419883563,
          "median": -0.05955259975816203,
          "min": -0.12953020134228188,
          "max": -0.015748031496062992
        }
      },
      "barriers": {
        "0.03/0.03": {
          "DOWNSIDE_FIRST": 2,
          "UPSIDE_FIRST": 2,
          "NEITHER": 1
        },
        "0.05/0.03": {
          "DOWNSIDE_FIRST": 3,
          "NEITHER": 1,
          "UPSIDE_FIRST": 1
        },
        "0.10/0.05": {
          "DOWNSIDE_FIRST": 3,
          "NEITHER": 1,
          "UPSIDE_FIRST": 1
        }
      },
      "excursion_events": 5,
      "excursion_censored": 2
    }
  },
  {
    "cycle_id": "2026-06-01",
    "selected": 24,
    "complete": 24,
    "observed_first_denominator": 24,
    "events": 6,
    "verified_events": 6,
    "zero_event": 18,
    "sessions": {
      "AH": 3,
      "PRE": 2,
      "RTH": 1
    },
    "primary_outcomes": {
      "forward": {
        "5m": {
          "events": 6,
          "uncensored": 2,
          "censored": 4,
          "mean": -0.03501541835948655,
          "median": -0.03501541835948655,
          "min": -0.06224457717698837,
          "max": -0.0077862595419847325
        },
        "15m": {
          "events": 6,
          "uncensored": 2,
          "censored": 4,
          "mean": -0.04770088462587581,
          "median": -0.04770088462587581,
          "min": -0.08802263439170073,
          "max": -0.007379134860050891
        },
        "30m": {
          "events": 6,
          "uncensored": 1,
          "censored": 5,
          "mean": -0.043256997455470736,
          "median": -0.043256997455470736,
          "min": -0.043256997455470736,
          "max": -0.043256997455470736
        },
        "60m": {
          "events": 6,
          "uncensored": 0,
          "censored": 6,
          "mean": null,
          "median": null,
          "min": null,
          "max": null
        },
        "session_end": {
          "events": 6,
          "uncensored": 2,
          "censored": 4,
          "mean": -0.0675488128063174,
          "median": -0.0675488128063174,
          "min": -0.0969296866813371,
          "max": -0.03816793893129771
        },
        "cycle_end": {
          "events": 6,
          "uncensored": 3,
          "censored": 3,
          "mean": -0.03557670102398757,
          "median": -0.03816793893129771,
          "min": -0.14788732394366197,
          "max": 0.07932515980299697
        }
      },
      "barriers": {
        "0.03/0.03": {
          "DOWNSIDE_FIRST": 6
        },
        "0.05/0.03": {
          "DOWNSIDE_FIRST": 6
        },
        "0.10/0.05": {
          "DOWNSIDE_FIRST": 5,
          "CENSORED": 1
        }
      },
      "excursion_events": 6,
      "excursion_censored": 3
    }
  },
  {
    "cycle_id": "2026-06-02",
    "selected": 24,
    "complete": 24,
    "observed_first_denominator": 24,
    "events": 3,
    "verified_events": 3,
    "zero_event": 21,
    "sessions": {
      "PRE": 2,
      "RTH": 1
    },
    "primary_outcomes": {
      "forward": {
        "5m": {
          "events": 3,
          "uncensored": 1,
          "censored": 2,
          "mean": -0.017111222949169603,
          "median": -0.017111222949169603,
          "min": -0.017111222949169603,
          "max": -0.017111222949169603
        },
        "15m": {
          "events": 3,
          "uncensored": 2,
          "censored": 1,
          "mean": -0.023550560658669843,
          "median": -0.023550560658669843,
          "min": -0.03271263210870659,
          "max": -0.014388489208633094
        },
        "30m": {
          "events": 3,
          "uncensored": 2,
          "censored": 1,
          "mean": 0.014223749334704355,
          "median": 0.014223749334704355,
          "min": -0.03597122302158273,
          "max": 0.06441872169099144
        },
        "60m": {
          "events": 3,
          "uncensored": 1,
          "censored": 2,
          "mean": 0.12279818822345244,
          "median": 0.12279818822345244,
          "min": 0.12279818822345244,
          "max": 0.12279818822345244
        },
        "session_end": {
          "events": 3,
          "uncensored": 2,
          "censored": 1,
          "mean": 0.47149095016890363,
          "median": 0.47149095016890363,
          "min": -0.007194244604316547,
          "max": 0.9501761449421238
        },
        "cycle_end": {
          "events": 3,
          "uncensored": 3,
          "censored": 0,
          "mean": 0.09705462368435809,
          "median": -0.007194244604316547,
          "min": -0.08362477311966002,
          "max": 0.38198288877705083
        }
      },
      "barriers": {
        "0.03/0.03": {
          "UPSIDE_FIRST": 1,
          "DOWNSIDE_FIRST": 2
        },
        "0.05/0.03": {
          "UPSIDE_FIRST": 1,
          "DOWNSIDE_FIRST": 2
        },
        "0.10/0.05": {
          "UPSIDE_FIRST": 1,
          "NEITHER": 1,
          "DOWNSIDE_FIRST": 1
        }
      },
      "excursion_events": 3,
      "excursion_censored": 0
    }
  },
  {
    "cycle_id": "2026-06-03",
    "selected": 24,
    "complete": 24,
    "observed_first_denominator": 24,
    "events": 3,
    "verified_events": 3,
    "zero_event": 21,
    "sessions": {
      "AH": 1,
      "PRE": 1,
      "RTH": 1
    },
    "primary_outcomes": {
      "forward": {
        "5m": {
          "events": 3,
          "uncensored": 3,
          "censored": 0,
          "mean": -0.05335067088798432,
          "median": -0.025852878464818763,
          "min": -0.11904761904761904,
          "max": -0.015151515151515152
        },
        "15m": {
          "events": 3,
          "uncensored": 3,
          "censored": 0,
          "mean": -0.051810320690917705,
          "median": -0.04584221748400853,
          "min": -0.10317460317460317,
          "max": -0.006414141414141414
        },
        "30m": {
          "events": 3,
          "uncensored": 2,
          "censored": 1,
          "mean": -0.029570760914044498,
          "median": -0.029570760914044498,
          "min": -0.04904051172707889,
          "max": -0.010101010101010102
        },
        "60m": {
          "events": 3,
          "uncensored": 3,
          "censored": 0,
          "mean": -0.08147103587402095,
          "median": -0.08635394456289978,
          "min": -0.14285714285714285,
          "max": -0.015202020202020203
        },
        "session_end": {
          "events": 3,
          "uncensored": 2,
          "censored": 1,
          "mean": -0.07377344877344877,
          "median": -0.07377344877344877,
          "min": -0.07936507936507936,
          "max": -0.06818181818181818
        },
        "cycle_end": {
          "events": 3,
          "uncensored": 2,
          "censored": 1,
          "mean": -0.06300881953867028,
          "median": -0.06300881953867028,
          "min": -0.06818181818181818,
          "max": -0.05783582089552239
        }
      },
      "barriers": {
        "0.03/0.03": {
          "UPSIDE_FIRST": 1,
          "DOWNSIDE_FIRST": 2
        },
        "0.05/0.03": {
          "UPSIDE_FIRST": 1,
          "DOWNSIDE_FIRST": 2
        },
        "0.10/0.05": {
          "DOWNSIDE_FIRST": 3
        }
      },
      "excursion_events": 3,
      "excursion_censored": 1
    }
  },
  {
    "cycle_id": "2026-06-04",
    "selected": 24,
    "complete": 24,
    "observed_first_denominator": 24,
    "events": 4,
    "verified_events": 4,
    "zero_event": 20,
    "sessions": {
      "AH": 1,
      "RTH": 3
    },
    "primary_outcomes": {
      "forward": {
        "5m": {
          "events": 4,
          "uncensored": 2,
          "censored": 2,
          "mean": 0.014637703087287006,
          "median": 0.014637703087287006,
          "min": -0.014373716632443531,
          "max": 0.04364912280701754
        },
        "15m": {
          "events": 4,
          "uncensored": 3,
          "censored": 1,
          "mean": 0.01572010136194725,
          "median": 0.006993006993006993,
          "min": 0.0017111567419575632,
          "max": 0.038456140350877195
        },
        "30m": {
          "events": 4,
          "uncensored": 2,
          "censored": 2,
          "mean": 0.006842609604092366,
          "median": 0.006842609604092366,
          "min": 0.0027378507871321013,
          "max": 0.010947368421052631
        },
        "60m": {
          "events": 4,
          "uncensored": 3,
          "censored": 1,
          "mean": 0.03640281675167658,
          "median": 0.03182751540041068,
          "min": 0.010947368421052631,
          "max": 0.06643356643356643
        },
        "session_end": {
          "events": 4,
          "uncensored": 3,
          "censored": 1,
          "mean": -0.01999871084881352,
          "median": -0.02097902097902098,
          "min": -0.064,
          "max": 0.024982888432580425
        },
        "cycle_end": {
          "events": 4,
          "uncensored": 3,
          "censored": 1,
          "mean": -0.01999871084881352,
          "median": -0.02097902097902098,
          "min": -0.064,
          "max": 0.024982888432580425
        }
      },
      "barriers": {
        "0.03/0.03": {
          "CENSORED": 1,
          "UPSIDE_FIRST": 3
        },
        "0.05/0.03": {
          "CENSORED": 1,
          "UPSIDE_FIRST": 3
        },
        "0.10/0.05": {
          "CENSORED": 1,
          "NEITHER": 2,
          "DOWNSIDE_FIRST": 1
        }
      },
      "excursion_events": 4,
      "excursion_censored": 1
    }
  },
  {
    "cycle_id": "2026-06-05",
    "selected": 24,
    "complete": 24,
    "observed_first_denominator": 24,
    "events": 2,
    "verified_events": 2,
    "zero_event": 22,
    "sessions": {
      "RTH": 1,
      "AH": 1
    },
    "primary_outcomes": {
      "forward": {
        "5m": {
          "events": 2,
          "uncensored": 2,
          "censored": 0,
          "mean": 0.06240059608480661,
          "median": 0.06240059608480661,
          "min": -0.058596491228070174,
          "max": 0.1833976833976834
        },
        "15m": {
          "events": 2,
          "uncensored": 2,
          "censored": 0,
          "mean": -0.04307627176048229,
          "median": -0.04307627176048229,
          "min": -0.051403508771929826,
          "max": -0.03474903474903475
        },
        "30m": {
          "events": 2,
          "uncensored": 2,
          "censored": 0,
          "mean": -0.007977714556661925,
          "median": -0.007977714556661925,
          "min": -0.04298245614035088,
          "max": 0.02702702702702703
        },
        "60m": {
          "events": 2,
          "uncensored": 1,
          "censored": 1,
          "mean": 0.02895752895752896,
          "median": 0.02895752895752896,
          "min": 0.02895752895752896,
          "max": 0.02895752895752896
        },
        "session_end": {
          "events": 2,
          "uncensored": 2,
          "censored": 0,
          "mean": -0.004595949332791439,
          "median": -0.004595949332791439,
          "min": -0.062280701754385964,
          "max": 0.05308880308880309
        },
        "cycle_end": {
          "events": 2,
          "uncensored": 1,
          "censored": 1,
          "mean": -0.062280701754385964,
          "median": -0.062280701754385964,
          "min": -0.062280701754385964,
          "max": -0.062280701754385964
        }
      },
      "barriers": {
        "0.03/0.03": {
          "DOWNSIDE_FIRST": 2
        },
        "0.05/0.03": {
          "DOWNSIDE_FIRST": 2
        },
        "0.10/0.05": {
          "DOWNSIDE_FIRST": 2
        }
      },
      "excursion_events": 2,
      "excursion_censored": 1
    }
  },
  {
    "cycle_id": "2026-06-08",
    "selected": 24,
    "complete": 24,
    "observed_first_denominator": 24,
    "events": 4,
    "verified_events": 4,
    "zero_event": 20,
    "sessions": {
      "RTH": 4
    },
    "primary_outcomes": {
      "forward": {
        "5m": {
          "events": 4,
          "uncensored": 3,
          "censored": 1,
          "mean": -0.0013938386656212947,
          "median": -0.0047875523638539795,
          "min": -0.03592814371257485,
          "max": 0.036534180079564944
        },
        "15m": {
          "events": 4,
          "uncensored": 2,
          "censored": 2,
          "mean": 0.015173059625615031,
          "median": 0.015173059625615031,
          "min": -0.009874326750448833,
          "max": 0.04022044600167889
        },
        "30m": {
          "events": 4,
          "uncensored": 4,
          "censored": 0,
          "mean": 0.0033670119506405754,
          "median": 0.002354083464624629,
          "min": -0.08982035928143713,
          "max": 0.09858024015475017
        },
        "60m": {
          "events": 4,
          "uncensored": 2,
          "censored": 2,
          "mean": 0.0903647887658954,
          "median": 0.0903647887658954,
          "min": -0.0017953321364452424,
          "max": 0.18252490966823606
        },
        "session_end": {
          "events": 4,
          "uncensored": 4,
          "censored": 0,
          "mean": 0.03214587645753883,
          "median": -0.026755944747737515,
          "min": -0.08802395209580838,
          "max": 0.2701193474214387
        },
        "cycle_end": {
          "events": 4,
          "uncensored": 4,
          "censored": 0,
          "mean": 0.03214587645753883,
          "median": -0.026755944747737515,
          "min": -0.08802395209580838,
          "max": 0.2701193474214387
        }
      },
      "barriers": {
        "0.03/0.03": {
          "UPSIDE_FIRST": 2,
          "DOWNSIDE_FIRST": 2
        },
        "0.05/0.03": {
          "UPSIDE_FIRST": 2,
          "DOWNSIDE_FIRST": 2
        },
        "0.10/0.05": {
          "UPSIDE_FIRST": 1,
          "NEITHER": 2,
          "DOWNSIDE_FIRST": 1
        }
      },
      "excursion_events": 4,
      "excursion_censored": 0
    }
  },
  {
    "cycle_id": "2026-06-09",
    "selected": 24,
    "complete": 24,
    "observed_first_denominator": 24,
    "events": 4,
    "verified_events": 4,
    "zero_event": 20,
    "sessions": {
      "RTH": 3,
      "AH": 1
    },
    "primary_outcomes": {
      "forward": {
        "5m": {
          "events": 4,
          "uncensored": 1,
          "censored": 3,
          "mean": -0.025089605734767026,
          "median": -0.025089605734767026,
          "min": -0.025089605734767026,
          "max": -0.025089605734767026
        },
        "15m": {
          "events": 4,
          "uncensored": 1,
          "censored": 3,
          "mean": -0.01971326164874552,
          "median": -0.01971326164874552,
          "min": -0.01971326164874552,
          "max": -0.01971326164874552
        },
        "30m": {
          "events": 4,
          "uncensored": 2,
          "censored": 2,
          "mean": -0.006322500884841053,
          "median": -0.006322500884841053,
          "min": -0.02698191933240612,
          "max": 0.014336917562724014
        },
        "60m": {
          "events": 4,
          "uncensored": 1,
          "censored": 3,
          "mean": -0.02146953405017921,
          "median": -0.02146953405017921,
          "min": -0.02146953405017921,
          "max": -0.02146953405017921
        },
        "session_end": {
          "events": 4,
          "uncensored": 2,
          "censored": 2,
          "mean": -0.058435152367136756,
          "median": -0.058435152367136756,
          "min": -0.07347670250896057,
          "max": -0.04339360222531293
        },
        "cycle_end": {
          "events": 4,
          "uncensored": 2,
          "censored": 2,
          "mean": -0.058435152367136756,
          "median": -0.058435152367136756,
          "min": -0.07347670250896057,
          "max": -0.04339360222531293
        }
      },
      "barriers": {
        "0.03/0.03": {
          "CENSORED": 2,
          "DOWNSIDE_FIRST": 2
        },
        "0.05/0.03": {
          "CENSORED": 2,
          "DOWNSIDE_FIRST": 2
        },
        "0.10/0.05": {
          "CENSORED": 2,
          "DOWNSIDE_FIRST": 2
        }
      },
      "excursion_events": 4,
      "excursion_censored": 2
    }
  }
]

## Research limits

All statistics cover the complete selected pilot sample, not the full historical universe. Sampling uses each cycle's M1 population, current identity-matched free-float proxy and complementary strata. Current float is not historical PIT: survivorship, dilution, reverse splits and later changes may misclassify past float. Missing current identity/float stays unresolved in the complementary control stratum. SEC evidence is independent, never forward-filled. No diagnostic securities were selected using future movement. Cohorts overlap; repeated securities, policy sensitivities and session risk sets must not be summed as independent observations. No population confidence intervals, threshold optimization or profitability inference is attempted. Weights and frame denominators are preserved for future design-aware analysis.

Primary returns use HIGH_LOW_ONLY eligible observed trades, wall-clock horizons, 60-second mark freshness and no automatic elapsed-gap censoring. Overnight, missing pages, unknown path evidence and corrections still censor. The 300/900-second rules and odd lots are separately labeled sensitivities. Observed MFE/MAE are not executable fills. Strict full-cycle findings remain unavailable. NBBO is bounded context; trade-above-ask flags remain in event data. P0 inherits M1 grouped daily close, not independently certified official auction close. No holdout observations were analyzed.

## Reproduction

`python -m market_lab.systematic_pilot run --offline` resumes immutable checkpoints. `validate --offline` independently checks page chains, raw events, NBBO and deterministic outcomes. `python scripts/query_systematic_pilot.py --kind events --ticker SYMBOL` provides bounded extracts; complete Parquet remains local. Code/config/source hashes and selection freeze are under data/runs/m2-systematic-10cycles-20261115-v2.

## Executed validation

{
  "status": "PASS",
  "checks": {
    "complete_windows": 302,
    "opportunities_replayed": 240,
    "outcomes_replayed": 249,
    "events_replayed": 83
  },
  "raw_tick_pages_checked": 334,
  "protected_files_unchanged": 1917,
  "holdout_analyzed": false,
  "source_code_hashes_match": true
}
