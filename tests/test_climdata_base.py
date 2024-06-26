"""
Unit tests for the _base module of the climdata subpackage.
"""

from unittest.mock import patch

import pytest

from climepi import climdata


class TestGetClimateData:
    """
    Class to test the get_climate_data function.
    """

    @pytest.mark.parametrize("data_source", ["test", "lens2", "isimip"])
    def test_get_climate_data_main(self, data_source):
        """
        Main test for the get_climate_data function.
        """
        frequency = "hourly"
        subset = {
            "scenarios": ["overcast", "sunny"],
            "models": ["length", "inswinger"],
            "realizations": [1, 2],
            "years": [2015, 2016, 2018, 2100],
            "location": "gabba",
            "lon_range": None,
            "lat_range": None,
        }
        save_dir = "not/real"
        download = "probably"
        force_remake = "perhaps"
        max_subset_wait_time = 30

        def _mock_get_data(self, **kwargs):
            if data_source == "lens2":
                assert (
                    getattr(self, "_max_subset_wait_time", "should not be here")
                    == "should not be here"
                )
            elif data_source == "isimip":
                assert self._max_subset_wait_time == max_subset_wait_time
            assert self._frequency == frequency
            assert self._subset == subset
            assert str(self._save_dir) == save_dir
            assert kwargs["download"] == download
            assert kwargs["force_remake"] == force_remake
            return "scoop"

        if data_source == "test":
            with pytest.raises(ValueError):
                climdata.get_climate_data(
                    data_source,
                    frequency=frequency,
                    subset=subset,
                    save_dir=save_dir,
                    download=download,
                    force_remake=force_remake,
                    max_subset_wait_time=max_subset_wait_time,
                )
            return
        if data_source == "lens2":
            to_patch = climdata._cesm.CESMDataGetter
        elif data_source == "isimip":
            to_patch = climdata._isimip.ISIMIPDataGetter
        with patch.object(to_patch, "get_data", new=_mock_get_data):
            result = climdata.get_climate_data(
                data_source,
                frequency=frequency,
                subset=subset,
                save_dir=save_dir,
                download=download,
                force_remake=force_remake,
                max_subset_wait_time=max_subset_wait_time,
            )
            assert result == "scoop"

    def test_get_climate_data_with_location_list(self):
        """
        Test the get_climate_data function with a location list. This involves calling
        a different method, _get_climate_data_location_list, which is mocked here and
        tested in detail in a separate test.
        """
        subset = {
            "location": ["gabba", "waca"],
        }

        def _mock_get_climate_data_location_list(**kwargs):
            assert kwargs["subset"] == subset
            return "flat"

        with patch.object(
            climdata._base,
            "_get_climate_data_location_list",
            new=_mock_get_climate_data_location_list,
        ):
            result = climdata.get_climate_data("test", subset=subset)
            assert result == "flat"


def test_get_climate_data_file_names():
    """
    Test the get_climate_data_file_names function, using a location list (which involves
    calling the function recursively with each location in the list).
    """
    data_source = "isimip"
    frequency = "monthly"
    subset = {
        "scenarios": ["overcast"],
        "models": ["length", "inswinger"],
        "realizations": [3],
        "years": [2015],
        "location": ["gabba", "mcg"],
    }
    result = climdata.get_climate_data_file_names(
        data_source, frequency=frequency, subset=subset
    )
    expected = [
        "isimip_monthly_2015_to_2015_" + comb + ".nc"
        for comb in [
            "gabba_overcast_length_3",
            "gabba_overcast_inswinger_3",
            "mcg_overcast_length_3",
            "mcg_overcast_inswinger_3",
        ]
    ]
    assert sorted(result) == sorted(expected)


@pytest.mark.parametrize("data_source", ["lens2", "isimip", "test"])
def test_get_data_getter(data_source):
    """
    Test the _get_data_getter function.
    """
    frequency = "hourly"
    subset = {
        "scenarios": ["overcast", "sunny"],
        "models": ["length", "inswinger"],
        "realizations": [1, 2],
        "years": [2015, 2016, 2018, 2100],
        "location": "gabba",
        "lon_range": None,
        "lat_range": None,
    }
    save_dir = "not/real"
    download = "probably"
    force_remake = "perhaps"
    max_subset_wait_time = 30
    if data_source == "test":
        with pytest.raises(ValueError):
            climdata._base._get_data_getter(
                data_source,
                frequency=frequency,
                subset=subset,
                save_dir=save_dir,
                download=download,
                force_remake=force_remake,
                max_subset_wait_time=max_subset_wait_time,
            )
        return
    result = climdata._base._get_data_getter(
        data_source,
        frequency=frequency,
        subset=subset,
        save_dir=save_dir,
        max_subset_wait_time=max_subset_wait_time,
    )
    if data_source == "lens2":
        assert isinstance(result, climdata._cesm.CESMDataGetter)
        assert (
            getattr(result, "_max_subset_wait_time", "should not be here")
            == "should not be here"
        )
    elif data_source == "isimip":
        assert isinstance(result, climdata._isimip.ISIMIPDataGetter)
        assert result._max_subset_wait_time == max_subset_wait_time
    else:
        raise ValueError("Should not be here.")
    assert result._frequency == frequency
    assert result._subset == subset
    assert str(result._save_dir) == save_dir
