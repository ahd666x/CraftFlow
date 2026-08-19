from django.test import TestCase
from unittest.mock import patch
import jdatetime

from product.utils import is_working_day


class IsWorkingDayTests(TestCase):
    def test_friday_is_not_working_day(self):
        friday = jdatetime.date.today()
        while friday.weekday() != 6:  # جمعه
            friday = jdatetime.date.fromgregorian(date=friday.togregorian() + __import__('datetime').timedelta(days=1))
        with patch('product.utils.Holiday.objects.filter') as mock_holiday:
            mock_holiday.return_value.exists.return_value = False
            self.assertFalse(is_working_day(friday))

    def test_saturday_is_working_day(self):
        saturday = jdatetime.date.today()
        while saturday.weekday() != 0:  # شنبه
            saturday = jdatetime.date.fromgregorian(date=saturday.togregorian() + __import__('datetime').timedelta(days=1))
        with patch('product.utils.Holiday.objects.filter') as mock_holiday:
            mock_holiday.return_value.exists.return_value = False
            self.assertTrue(is_working_day(saturday))

    def test_holiday_is_not_working_day(self):
        saturday = jdatetime.date.today()
        while saturday.weekday() != 0:
            saturday = jdatetime.date.fromgregorian(date=saturday.togregorian() + __import__('datetime').timedelta(days=1))
        with patch('product.utils.Holiday.objects.filter') as mock_holiday:
            mock_holiday.return_value.exists.return_value = True
            self.assertFalse(is_working_day(saturday))

    def test_wednesday_is_working_day(self):
        wednesday = jdatetime.date.today()
        while wednesday.weekday() != 3:  # چهارشنبه
            wednesday = jdatetime.date.fromgregorian(date=wednesday.togregorian() + __import__('datetime').timedelta(days=1))
        with patch('product.utils.Holiday.objects.filter') as mock_holiday:
            mock_holiday.return_value.exists.return_value = False
            self.assertTrue(is_working_day(wednesday))
